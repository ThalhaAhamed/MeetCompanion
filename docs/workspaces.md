# Workspaces and export

## Workspaces

One account can belong to several workspaces and switch between them from the
picker in the top bar (the workspace name next to the theme toggle).

Everything is scoped to the workspace you currently have open - meetings,
notes, memory, action items - so switching changes what you see. Your role
travels with the workspace too: you can own one and be a plain member of
another.

From the workspace picker you can **create** another workspace (you own it) or
**join** one with a code (you are a member - ownership stays with whoever made
it). Both attach to the account you are already signed in as, so there is no
second login to keep track of.

Your first workspace is created for you at sign-up. Nothing needs converting to
share it: hand someone the join code from **Members** and it becomes a shared
workspace. Owners decide what members may do there — add, edit, delete,
manage agents, export, invite — from the same page.

<div align="center">
<img src="media/workspaces.gif" alt="On the Members page an owner switches on Delete content and Invite people for members, then opens the workspace picker, creates a second workspace and switches back" width="900" />
</div>

What is shared and what is not:

| Shared across the workspace | Stays yours alone |
| --- | --- |
| Meetings, transcripts, memories, action items | Your MeetStream API key (bots bill to you) |
| Notes, folders, documents, knowledge graph | Your agent |
| Search and Ask AI results | Your LLM provider and key (per install) |

## Export

Your notes and meetings come back out in formats that outlive the app.

| Where | What you get |
| --- | --- |
| A note (Notebook -> export) | `.md` with YAML front matter, or `.json` |
| A meeting (Meetings -> Export) | `.md` with summary, decisions, action items and transcript, or `.json` |
| Everything (Settings -> General) | `.zip` of Markdown that keeps your folder tree, or one `.json` |

Markdown is written for reading and for dropping straight into Obsidian or
Notion - front matter carries the title, tags, folder and dates. JSON is the
lossless one: ids, metadata and the raw note text, so an export can be
processed or re-imported by something else.
