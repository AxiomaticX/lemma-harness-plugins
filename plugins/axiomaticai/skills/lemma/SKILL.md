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

Start a conversation with `create_conversation`, writing the task as you would brief a
colleague: the goal, what you already know, and what a good result looks like. Continue it with
`send_message` and the conversation's id.

- `mode` is required when you start: `act` to work straight away, or `plan` to have Lemma draft a
  plan the user approves before any work runs. Use `plan` when the user asks for it, or for a
  long or costly study they should shape first. A conversation keeps its mode; pass `mode` to
  `send_message` only to change it.
- `model`, `provider` and `machine` follow the user's defaults when left out. `list_options`
  shows what the user can choose and what each machine costs. The machine is fixed once a
  conversation starts. Choose any of these only when the user asks.
- Pass local files in `files`, as paths. Relative paths resolve against the project directory.
  They are uploaded first and land in the conversation's workspace.

Both return `conversation_id`, `run_id` and `url`. Keep all three.

## Ready-made workflows

Lemma has ready-made workflows for common jobs, such as surveying the literature, making a paper
interactive, verifying a paper's references or simulating a device. `list_workflows` lists them
with the inputs each asks for. When the user's request matches one, start it with
`start_workflow`, its inputs, and any files it needs as local paths. Ask the user for a required
input you don't have rather than guessing it.

## Decisions are the user's

Lemma sometimes stops for a decision: a question in its plan, approval of the plan, a review of
a finished task, or approval of a step mid-run. Each one is the user's to make. Put the question
to them, with Lemma's default where it gave one, and act only on their answer. When the user has
told you in advance how to decide, such as "use the defaults", say what you decided for them.

## Plan mode

A run in plan mode ends with a draft plan, not the work. After it:

1. `get_plan` reads the plan: its tasks, the questions it asks with default answers, and the
   finished tasks waiting for review. Tell the user what it plans and what it asks.
2. `answer_plan` sends their answers, and with `approve` true approves the plan as answered.
3. `run_plan` runs it: `all` runs every task until one needs the user, `next` just the next one.
4. When a task finishes and waits for review, `review_task` approves, disapproves or waives it.

## Wait for the run

Runs take minutes, and long ones take hours. Do not poll in a loop.

- After any call that starts a run, you are woken when the run ends, so carry on with other
  work. If it is still going after `wake_after_minutes` (60 by default), you are woken with word of that
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
| `waiting_for_input` | Lemma needs a decision only the user can make; `questions` holds it. | Ask the user, then `answer_questions` with their decision. In plan mode, check `get_plan` for reviews too. |
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
