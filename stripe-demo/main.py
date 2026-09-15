"""Prepaid streaming chat: FastHTML, fastlite, fastllm and faststripe. One worker."""
import asyncio, json, os, secrets
from collections import defaultdict
from math import ceil
from uuid import uuid4

from fasthtml.common import *
from fasthtml.oauth import GoogleAppClient, OAuth
from fastlite import *
from fastllm.chat import AsyncChat, Text
from faststripe.core import StripeApi, StripeError
from fasthtml.components import Billing_Card, Card_Label
from dotenv import load_dotenv

load_dotenv()


class User: id: str; email: str; customer: str = ''; pm: str = ''; last4: str = ''; auto_on: bool = False; amount: int = 1000; threshold: int = 200
class Entry: id: str; uid: str; amount: int; memo: str
class Turn: id: str; uid: str; prompt: str; answer: str = ''; cost: int = 0


db = database('chat.db')
users, ledger, turns = db.create(User), db.create(Entry), db.create(Turn)
sapi = StripeApi(service_name='naur-chat')
model =  'anthropic/claude-sonnet-5'
locks, jobs, tasks = defaultdict(asyncio.Lock), {}, set()
def balance(uid): return sum(e.amount for e in ledger('uid=?', [uid]))
def money(micros, prec=2): return f'${micros / 1_000_000:,.{prec}f}'


SCROLL = "const m=document.getElementById('messages');new MutationObserver(()=>m.scrollTo(0,m.scrollHeight)).observe(m,{childList:true,subtree:true,characterData:true});m.scrollTo(0,m.scrollHeight)"

def invalid(req, exc): return HTMLResponse(to_xml(P(str(exc))), headers={'HX-Retarget': '#status', 'HX-Reswap': 'innerHTML'})


app, rt = fast_app(pico=False, secret_key=os.getenv('SESSION_SECRET') or None,
    exception_handlers={ValueError: invalid, StripeError: invalid},
    hdrs=(Script(src='https://js.stripe.com/v3/'), Script(f'var stripe = Stripe({sapi.publishable_key!r});'),
          Script(src='https://cdn.jsdelivr.net/npm/htmx-ext-sse@2.2.4/dist/sse.js'),
          Link(rel='stylesheet', href='/assets/styles.css')))

## OAuth and login

class Auth(OAuth):
    def get_auth(self, info, ident, session, state):
        if not state or not secrets.compare_digest(session.pop('oauth_state', ''), state): return
        if not info.get('email_verified'): return
        if ident in users: users.update(id=ident, email=info.email)
        else: users.insert(User(id=ident, email=info.email))
        return RedirectResponse('/', status_code=303)

    def check_invalid(self, req, session, auth):
        if auth not in users: return self.redir_login(session)

oauth = Auth(app, GoogleAppClient(os.environ['GOOGLE_CLIENT_ID'], os.environ['GOOGLE_CLIENT_SECRET']), skip=['/login', '/redirect', '/error', r'/assets/.*'])

@rt('/login')
def login(req, session):
    session.setdefault('oauth_state', secrets.token_urlsafe(32))
    return Title('Credit Chat · Sign in'), Main(Billing_Card(Card_Label('Credit Chat'), P('Add credit. Start a conversation.'),
        A('Sign in with Google', href=oauth.login_link(req, state=session['oauth_state']), cls='btn')), cls='login')


@rt('/error')
def error(): return Main(Billing_Card(P('Sign-in did not complete.'), A('Try again', href='/login', cls='btn')), cls='login')


async def csrf(req, session):
    if req.method == 'POST' and not secrets.compare_digest(session.get('csrf', ''), req.headers.get('x-csrf-token', 'missing')):
        return Response('Please reload the page.', status_code=403)
app.before.append(Beforeware(csrf))

## Billing and card setup

@rt('/card/setup', methods=['POST'])
async def card_setup(auth):
    u = users[auth]
    if not u.customer:
        c = await sapi.v1.customers.post(email=u.email)
        u = users.update(id=auth, customer=c.id)
    si = await sapi.v1.setup_intents.post(customer=u.customer, usage='off_session', payment_method_types=['card'])
    return Div(id='card-element'), P('Saving authorizes your card for manual and enabled automatic top-ups.'), \
        Button('Save card', primary=True, onclick='saveCard()'), Script(f"""
        var card = stripe.elements().create('card', {{disableLink:true}});
        card.mount('#card-element');
        async function saveCard() {{
            const {{error, setupIntent}} = await stripe.confirmCardSetup({si.client_secret!r}, {{payment_method:{{card}}}});
            if (error) return alert(error.message);
            htmx.ajax('POST', '/card/save', {{source:'#card-form', values:{{sid:setupIntent.id}}}});
        }}""")


@rt('/card/save', methods=['POST'])
async def card_save(auth, sid: str):
    si = await sapi.v1.setup_intents.intent.get(sid)
    if si.status != 'succeeded' or si.customer != users[auth].customer: raise ValueError('Card setup did not complete.')
    pm = await sapi.v1.payment_methods.payment_method.get(si.payment_method)
    users.update(id=auth, pm=pm.id, last4=pm.card.last4)
    return HtmxResponseHeaders(redirect='/')


def credit(uid, pi):
    if pi.customer != users[uid].customer or pi.currency != 'usd' or not sapi.filter_evt(pi): raise ValueError('Payment does not match this account.')
    if pi.status != 'succeeded' or pi.amount_received != pi.amount: raise ValueError('Payment has not completed.')
    with db.conn:
        if pi.id not in ledger: ledger.insert(Entry(id=pi.id, uid=uid, amount=pi.amount * 10_000, memo='Top-up'))


async def charge(uid, cents, off_session=False):
    "Charge `cents` to the saved card; `off_session` when nobody is present to authenticate"
    async with locks[uid]:
        u = users[uid]
        pi = await sapi.v1.payment_intents.post(customer=u.customer, amount=cents, currency='usd', payment_method=u.pm, confirm=True,
            off_session=off_session, payment_method_types=['card'], metadata={'STRIPE_SERVICE_NAME': sapi.service_name})
        if pi.status == 'succeeded': credit(uid, pi)
        return pi


@rt('/topup', methods=['POST'])
async def topup(auth, amount: int):
    if not 1 <= amount <= 500: raise ValueError('Choose $1–$500.')
    pi = await charge(auth, amount * 100)
    if pi.status != 'succeeded': raise ValueError('Payment needs authentication or was declined.')
    return HtmxResponseHeaders(redirect='/')


async def auto_topup(uid):
    "Top up from the saved card when auto top-up is on and credit is below the threshold"
    u = users[uid]
    if u.auto_on and balance(uid) < u.threshold * 10_000: await charge(uid, u.amount, off_session=True)


@rt('/auto', methods=['POST'])
def auto_config(auth, amount: int, threshold: int, on: bool = False):
    if not 1 <= amount <= 500 or not 1 <= threshold <= 500: raise ValueError('Choose $1–$500.')
    return billing(users.update(id=auth, auto_on=on, amount=amount * 100, threshold=threshold * 100))

async def generate(t):
    try:
        await auto_topup(t.uid)
        if balance(t.uid) <= 0: raise ValueError('Add credits first.')
        history = turns('uid=? and cost>0', [t.uid], order_by='rowid DESC', limit=10)
        hist = [dict(role=role, content=text) for h in reversed(history) for role, text in [('user', h.prompt), ('assistant', h.answer)]]
        chat = AsyncChat(model, hist=hist, markup=0.5, default_cbs=False, sp='Keep answers concise. Use plain text.')
        async for part in await chat(t.prompt, stream=True, max_tokens=512):
            if isinstance(part, Text): t.answer += part.text
        t.cost = ceil(chat.use.cost * 1_000_000)
        with db.conn:
            ledger.insert(Entry(id=t.id, uid=t.uid, amount=-t.cost, memo='Chat'))
            turns.update(t)
    except Exception as e: t.answer += f'\n{e}'
    finally:
        turns.update(t)
        jobs.pop(t.id, None)


## UI

def billing(u, oob=False):
    num = lambda name, value: Input(name=name, type='number', value=value, min=1, max=500, required=True)
    return Div(
        Billing_Card(Card_Label('Balance'), Div(money(balance(u.id)), cls='balance-big')),
        Billing_Card(Card_Label('Payment method'),
            Div(Span(f'•••• {u.last4}' if u.pm else 'No card on file', cls='pm-last'),
                A('Replace' if u.pm else 'Add card', href='#', hx_post='/card/setup', hx_target='#card-form', cls='replace-btn'), cls='pm-view'),
            Div(id='card-form')),
        Billing_Card(Form(
            Div(Card_Label('Auto top-up'), Label(Input(type='checkbox', name='on', checked=bool(u.auto_on)), cls='toggle-switch'), cls='topup-toggle'),
            Div(Label('Amount (US$)', num('amount', u.amount // 100)), Label('Trigger (US$)', num('threshold', u.threshold // 100)), cls='topup-row'),
            Button('Save', primary=True, disabled=not u.pm),
            cls='topup-nums', hx_post='/auto', hx_target='#billing', hx_swap='outerHTML')),
        Billing_Card(Card_Label('One-off top-up'),
            Form(Label('US$ ', num('amount', 10)), Button('Topup now', primary=True, disabled=not u.pm),
                cls='topup-nums', id='topup-form', hx_post='/topup', hx_target='#status', hx_disabled_elt='find button'),
            Div(id='status', cls='topup-status')),
        id='billing', cls='billing-cards', hx_swap_oob='outerHTML' if oob else None)


def composer(**kw):
    return Textarea(name='prompt', id='prompt', placeholder='Ask something…', required=True, rows=3,
        onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();this.form.requestSubmit()}", **kw)


def message(t):
    stream = dict(hx_ext='sse', sse_connect=f'/stream/{t.id}', sse_close='done') if t.id in jobs else {}
    return Div(P(t.prompt, cls='q'), Div(Div(t.answer, cls='answer'), Small(money(t.cost, 4), cls='cost'), sse_swap='message'), cls='turn', **stream)


@rt('/')
def index(auth, session):
    token = session.setdefault('csrf', secrets.token_urlsafe(32))
    u, history = users[auth], turns('uid=?', [auth], order_by='rowid')
    return Title('Credit Chat'), Main(
        Div(Span('Credit Chat'), Span(u.email, A('Sign out', href='/logout')), cls='topbar'),
        Div(billing(u),
            Section(Div(*map(message, history), id='messages', cls='messages'),
                Form(composer(), Button('Send', primary=True), cls='composer', hx_post='/chat', hx_target='#messages', hx_swap='beforeend', hx_disabled_elt='find button'),
                Div('Answers cost model price + 50%.', cls='hint'), cls='chat'),
            cls='layout'),
        Script(SCROLL), hx_headers=json.dumps({'X-CSRF-Token': token}))


@rt('/chat', methods=['POST'])
async def chat_start(auth, prompt: str):
    if any(t.uid == auth for t in jobs.values()): raise ValueError('Wait for the current response.')
    t = turns.insert(Turn(id=str(uuid4()), uid=auth, prompt=prompt))
    jobs[t.id] = t
    task = asyncio.create_task(generate(t))
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return message(t), composer(hx_swap_oob='outerHTML')


@rt('/stream/{tid}')
async def stream(tid: str, auth):
    t = jobs.get(tid) or turns.get(tid, default=None)
    if not t or t.uid != auth: return Response(status_code=404)
    async def events():
        while tid in jobs:
            yield sse_message(Div(t.answer, cls='answer'))
            await asyncio.sleep(0.05)
        yield sse_message((Div(t.answer, cls='answer'), Small(money(t.cost, 4), cls='cost'), billing(users[auth], oob=True)))
        yield sse_message('done', event='done')
    return EventStream(events())


if __name__ == '__main__': serve(host='127.0.0.1', port=int(os.getenv('PORT', '8000')), reload=True)
