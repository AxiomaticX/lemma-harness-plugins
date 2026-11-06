---
name: lemma
description: Hand a research, engineering or scientific computing task to Lemma, Axiomatic's agent, and bring its answer and result files back. Use when the user asks for Lemma, or wants a task done in Lemma and continued in the browser.
---

# Working with Lemma

Lemma is a separate agent that works in its own conversation, on its own machine, under the
user's Lemma account. Each message you send starts a run, and the usage is charged to that
account, the same as a message typed in the browser.

## Keep the user informed

The user sees none of what these tools return, and none of the wake-ups that tell you a run
ended. Everything they learn about Lemma comes from what you tell them.

- When you send a message, say what you asked Lemma to do and give them `url`.
- When a run ends, tell them its outcome and what Lemma answered, in your own words.
- When a call fails, pass Lemma's message on as it is, such as a model it refused, a plan that
  has run out, or a conversation that is busy, before you decide what to do next. Never retry
  with different options without saying so.

## Hand work over

Call `send_message` with the task written as you would brief a colleague: the goal, what you
already know, and what a good result looks like.

- Leave out `conversation_id` to start a new conversation. To continue one, pass the id
  `send_message` returned for it.
- Pass local files in `files`, as paths. Relative paths resolve against the project directory.
  They are uploaded first and land in the conversation's workspace.
- Use `model`, `plan_mode` and `machine` only when the user asks for them. `machine` takes
  effect only when a conversation starts.

`send_message` returns `conversation_id`, `run_id` and `url`. Keep all three.

## Wait for the run

Runs take minutes, and long ones take hours. Do not poll in a loop.

- After `send_message`, you are woken when the run ends, so carry on with other work. If it is
  still going after `wake_after_minutes` (60 by default), you are woken with word of that
  instead. Call `wait_for_result` then to keep waiting, which arms the next wake-up.
- Set `wake_after_minutes` higher only when you know the run will take hours, such as a long
  simulation or a whole plan.
- To block until the run ends, call `wait_for_result`. It returns as soon as the run ends, or
  after `timeout_s` seconds (600 at most) with outcome `running`.
- `get_result` reports the outcome at once without waiting.

## Read the outcome

| outcome | meaning | what to do |
| --- | --- | --- |
| `answered` | The run ended with a reply. | Use `answer`. |
| `running` | Still working. | Carry on; you are woken when it ends. |
| `waiting_for_input` | Lemma needs a decision only the user can make. | Give the user `url` to answer it in the browser. |
| `no_answer` | The run ended without a reply. | Give the user `url` to see what happened. |

Only one run can be active in a conversation. If `send_message` says the conversation is busy,
wait for the current run first, or start a new conversation.

## Bring results back

- `list_files` shows the conversation's files, including those Lemma produced. `ready` is false
  while one is still being written.
- `download_file` saves one by name or id into a local directory and returns the saved path. It
  never overwrites: a name already taken gets a numbered suffix.

## Hand over to the user

`url` opens the same conversation in Lemma in the browser, where the user can read every step
and continue it themselves. Offer it whenever the user should see or steer the work.

When the user asks to see a conversation, call `open_in_browser` with its id. If it returns
`opened` false, no browser could be opened: give them `url` instead.

## Sign-in

The first call that needs Lemma opens the browser to sign in, and the sign-in is remembered
across sessions. If no browser can be opened, the tool returns a link: show it to the user, and
call the tool again once they have signed in. `logout` signs out.
