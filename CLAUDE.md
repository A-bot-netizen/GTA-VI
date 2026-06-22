# Claude Instructions

Use uv for dependencies.

## Before implementing anything

Always propose the approach first and wait for confirmation before writing any code. Help the user with the best possible solution. Think like a senior software engineer. If available, give different solutions that resolve the users issue.

For every change request:
1. Explain what you think the problem is
2. Describe the approach you would take
3. List which files would be changed and what would change in each
4. Ask if this is the right direction before proceeding

Only start implementing after the user explicitly confirms (e.g. "yes", "go ahead", "looks good").

**When in doubt, ask a clarifying question rather than making an assumption.** If a request could be interpreted multiple ways, or if a choice would meaningfully affect the implementation, pause and ask before writing any code.

## Exceptions

Simple, clearly scoped changes (e.g. fixing a typo, adding a README section) can be done directly without a proposal.

## External API calls

Every source module that calls an external API must include:
- **Retry logic with exponential backoff** on 429 (rate limit) and 5xx responses
- **A delay between consecutive requests** to the same host (minimum 10–15 s between back-to-back calls to the same API)
- **A descriptive `User-Agent` header** where the API requires or recommends one
- **A `timeout`** on every `requests.get()` call (never an unbounded request)

The shared retry helper lives in `sources/_retry.py`. Use it rather than re-implementing backoff per source.
