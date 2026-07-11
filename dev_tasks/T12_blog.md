# Task T12: blog post for QuotePilot (Qwen Cloud hackathon Blog Award)

Write a technical blog post about building QuotePilot. Output ONE file:
`docs/blog.md`, Markdown, ~1100-1500 words. Voice: a builder sharing a genuinely
interesting story — specific, honest, a little opinionated. English.

The hook / unique angle: **"I had Qwen models build a Qwen-powered app — and
supervised them."** The app (an email-to-quote autopilot for cross-border B2B)
is itself powered by Qwen at runtime, AND was largely written by Qwen models
(qwen3-coder-plus for code, qwen-max for UI/copy, qwen-flash for small tasks)
dispatched through a small harness (scripts/qwen_dev.py) while a supervising
agent reviewed and accepted every output. Total model spend: under $1 of $40.

Weave in these REAL, concrete details (they make the post credible):
- Model routing: qwen-max = planner/bilingual drafting, qwen-flash = extraction
  & risk workers, qwen3-coder-plus = strict structured output + most of the code.
- The hard design line that makes it trustworthy: **LLMs never do arithmetic**
  (all pricing is Python Decimal) and **never write legal terms** (fixed
  bilingual clauses). This is the thesis: use LLMs for language, not ledgers.
- Honest war stories (do not sugarcoat): (a) Alibaba Cloud fcapp.run system
  domain force-downloads HTML and forbids 3xx redirects → we split into a static
  GitHub Pages SPA calling a CORS JSON API. (b) The custom.debian10 runtime
  shipped Python 3.7 despite docs promising 3.10 → switched to custom.debian12
  (Python 3.11). (c) Asking Qwen to re-emit a 70KB+ single-file frontend failed
  (it dropped 23KB and skipped the feature) — lesson: give a code model the
  CHANGED functions, not the whole file. (d) An adversarial multi-agent review
  round caught 11 real bugs (a discount field-name mismatch that 422'd every
  save, a stored-XSS in a settings field) before they shipped.
- The human-in-the-loop is the product's spine: approve / edit / reject, with the
  server re-pricing edits in Decimal. Judges' takeaway: autonomy WITH a brake.
- Close with a reflection on the workflow: what "AI writes the code, a human/agent
  reviews it" actually feels like, where it shines (mechanical breadth, UI), and
  where you must not let go of the wheel (money math, security, big-file edits).

Structure with subheadings. Include 1-2 short code-ish snippets or config lines
if they help (e.g. the Decimal pricing idea, or the model-routing table). End
with links: live demo https://mark24680617.github.io/quotepilot/ and repo
https://github.com/mark24680617/quotepilot . Do NOT invent metrics beyond what's
given here.
