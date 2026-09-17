# Why LLMs can't make your code simpler

Resources for my [Python Meetup Talk](https://www.meetup.com/python-barcelona/events/316366469/?eventOrigin=group_events_list) on September 2026.

## Abstract:

LLMs tend to increase the complexity of a codebase very fast, especially if left unchecked. If you're fine with that creeping complexity, this talk may not be for you. But if you have tried to tame it, you'll have noticed how hard it is. Why is that? Why can't LLMs write simple code? Couldn't frontier labs just train models to minimize total LoC, or cyclomatic complexity?

In Programming as Theory Building (1985), Peter Naur argues that the real program is not the code but the understanding in your head. That is one of the key problems for LLMs: the information needed to simplify code was never in the code to begin with. As a working example, I'll show how this mindset let us at Answer.AI cut our Stripe billing system down to ~300 lines of Python — and why this solution might also be good for you (or not!).


## Links

- Slides: [slides.pdf](slides.pdf) / [slides.html](slides.html) 
- Medium Post: [Why LLMs can't make your code simpler](https://medium.com/@pol.avec/why-llms-cant-make-your-code-simpler-fc2cd36bc0c8)
- Paper: [Programming as Theory Building](https://pages.cs.wisc.edu/~remzi/Naur.pdf), Peter Naur, 1985
- Read the paper with an LLM: [fork this Solveit dialog](https://share.solveit.pub/d/813cc704f8ce5f5f75b8fcd991fba816); [how close reading works](https://www.fast.ai/posts/2026-01-21-reading-LLMs/)
- Billing demo: [`stripe-demo/`](stripe-demo/), the payment system from the talk in one file: card on file at signup, manual and automatic top-ups, streaming chat. Its README says how to run it.

Reach me at: 
- https://x.com/pol_avec
- [Other talks & posts](https://justreadthe.info/)


