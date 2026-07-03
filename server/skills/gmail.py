"""OrphicOS skill pack: Gmail — in-app email expertise (paid add-on).

The expertise below is the proven Gmail flow lifted out of the brain's base
prompt (it drove the live-confirmed compose+send run), plus search/reply
recipes. Deepened on the `skill-gmail` branch toward its 3 flagship recipes:
compose+send to a named person, find+summarize recent mail from X, reply to
the latest thread.
"""

SKILL = {
    "id": "gmail",
    "title": "Gmail",
    "tagline": "Compose, send, search, summarize, and reply to email hands-free.",
    "checkout_path": "/skills/gmail",
    "classify": ("doing email work inside Gmail — composing, sending, replying to, "
                 "searching, or summarizing mail"),
    "expertise": """- To write an email in Gmail: navigate the browser to "gmail.com" (address-bar chain) and wait "2"; on
  the Gmail screen click "Compose", wait "1", then STOP that plan (done=false) — the compose pane is a new
  screen you must see before filling it. On the next turn the pane's To field already has keyboard focus: type
  the recipient (the address, or a person's name to use Gmail's contact suggestions), press "enter" to accept
  the top suggestion, press "tab" to reach Subject, type the subject, press "tab" to reach the message body,
  type the message — ALL in ONE plan. Write a clear subject and body yourself from the COMMAND's intent unless
  exact text is dictated. Finish that same plan by clicking the "Send" button with done=true; the client asks
  the user to approve the send, so the plan is safe to complete in one go.
- To find mail in Gmail: click the "Search mail" box, type the query (a sender's name, "from:someone", or a
  topic), press "enter", wait "1" — then read the result rows from the fresh tree (rows are named by sender,
  subject, and snippet). To open one, click its row.
- To summarize recent mail from someone: run the search above, then answer from the result rows' names — each
  row's name carries sender, subject, and a snippet, which is usually enough. Open a row only when the COMMAND
  needs detail beyond the snippet.
- To reply to the latest thread from someone: search for them, click the TOP result row, wait "1", then STOP
  (done=false) to see the conversation. On the next turn click "Reply", wait "1", STOP again — then type the
  reply into the focused box and click "Send" (the client gates the send behind user approval) with done=true.
- Compose/reply drafts do NOT survive between your turns unfilled — once a compose or reply box is open and
  focused, fill AND send it within a single plan.""",
}
