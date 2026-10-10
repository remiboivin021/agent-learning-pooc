# Engineering brain

An MCP server named `brain` holds lessons extracted from past merged PRs.

Before starting a task that changes code, call `brain_search_lessons` with a short
description of the situation (language, component, the problem you are solving).

How to use the results:
- Each lesson has a `status`. `candidate` and `contested` lessons are hypotheses:
  check them against the code in front of you, do not apply them blindly.
- Skip lessons whose `score` is low or whose context does not match the task.
- When a lesson changes what you do, say which one (its `title`) in your answer.

Lessons are written by the post-merge extraction job; the brain tools you have are read-only.
