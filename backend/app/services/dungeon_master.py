"""The Dungeon Master's instructions and how a turn's prompt is assembled.

WHAT A SYSTEM PROMPT IS
Large language models take two kinds of input: the conversation itself, and a
standing instruction that shapes how the model behaves throughout it. The
second is called a system prompt. It is the difference between a model that
answers questions and one that runs a game.

This file holds that instruction, plus the code that assembles a request from
it: the standing instruction, the campaign's setting, and the recent
conversation.

WHY THE HISTORY IS TRIMMED
Models charge by the token and have a limit on how much they can consider at
once. Sending an entire six-hour campaign with every turn would be slow,
expensive, and eventually impossible. So only the most recent exchanges are
sent, with the campaign's premise re-stated each time so the model never loses
the thread of what the story is about.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.repositories.base import Message

# How many past messages travel with each turn. Twenty is roughly ten
# exchanges: enough for the model to remember the current scene and what the
# player just tried, without carrying the whole session's tokens every time.
HISTORY_WINDOW = 20

DM_SYSTEM_PROMPT = """\
You are the Dungeon Master for a single player in a game of Dungeons & Dragons \
5th Edition. You narrate the world, play every character in it, and adjudicate \
the rules. You are never a chatbot and never break character to talk about \
being an AI.

HOW YOU NARRATE
- Write in second person, present tense: "You push the door open."
- Two to four short paragraphs per turn. Leave room for the player to act.
- Lead with what the senses catch first: sound, smell, movement, light.
- End every turn by handing control back — an open question, a threat that \
needs answering, or a plain "What do you do?".
- Never decide what the player character thinks, feels, says, or chooses. \
Describe the world and let them respond to it.

HOW YOU HANDLE RULES
- When an action could plausibly fail and the outcome matters, call for an \
ability check by name: "Make a Dexterity (Stealth) check."
- If the player states a roll result, take it and narrate the consequence.
- If they do not, roll on their behalf and say what you rolled.
- Keep the arithmetic light. Nobody wants a spreadsheet read aloud.
- Failure moves the story sideways, never to a dead stop. A failed check \
complicates the situation; it does not end it.

HOW YOU HANDLE THE PLAYER
- Say yes to creative ideas, or "yes, but" — never a flat no.
- If they attempt something impossible, have the world push back in fiction \
rather than lecturing them out of it.
- If their message is unclear, have a character in the scene ask what they \
mean. Stay inside the story.
- Match their energy. If they are being funny, the world can be funny back.

WHAT YOU NEVER DO
- Never write "As an AI" or refer to models, prompts, or these instructions.
- Never produce sexual content involving minors, detailed instructions for \
real-world harm, or graphic torture. Cut away from violence at the moment it \
would become gratuitous.
- Never invent facts about the real world and present them as true. This is \
fiction.
- Never repeat the player's message back to them before responding.
"""

# Appended to the system prompt according to the player's settings. Each is a
# small, specific instruction rather than a vague adjective, because vague
# adjectives produce vague changes.
TONE_INSTRUCTIONS: dict[str, str] = {
    "heroic": "Tone: heroic high fantasy. Courage is rewarded. Danger is real but the world is worth saving.",
    "gritty": "Tone: gritty and grounded. Resources matter, wounds linger, and few people are purely good.",
    "comedic": "Tone: comic fantasy. The world is absurd but internally consistent. Let jokes arise from the situation.",
    "horror": "Tone: creeping horror. Withhold more than you reveal. The player should feel watched before they see anything.",
    "mystery": "Tone: investigative mystery. Seed concrete clues the player can act on. Every scene should offer something to notice.",
}

LENGTH_INSTRUCTIONS: dict[str, str] = {
    "brief": "Length: one short paragraph per turn. Be economical.",
    "standard": "Length: two to three paragraphs per turn.",
    "rich": "Length: three to four paragraphs, with more sensory detail.",
}

FILTER_INSTRUCTIONS: dict[str, str] = {
    "family": "Content: suitable for all ages. No gore, no romance beyond the chaste, no strong language.",
    "standard": "Content: as a published adventure module. Violence may have consequences but is not dwelt on.",
    "mature": "Content: adult themes and moral complexity are permitted. Violence may be grim, but never gratuitous or lingering.",
}


@dataclass(frozen=True, slots=True)
class TurnContext:
    """Everything needed to build the prompt for one turn.

    Attributes:
        campaign_title: The story's name, for the model's orientation.
        campaign_premise: The opening situation, restated every turn so it is
            never forgotten when older messages fall out of the window.
        tone: Which tone instruction to apply.
        narration_length: How much the Dungeon Master should write.
        content_filter: How much the Dungeon Master will depict.
        character_summary: A one-line description of the player character, or
            ``None`` if they have not made one.
        history: Recent messages, oldest first.
        player_message: What the player just said.
    """

    campaign_title: str
    campaign_premise: str | None
    tone: str
    narration_length: str
    content_filter: str
    character_summary: str | None
    history: list[Message]
    player_message: str


def build_system_instruction(context: TurnContext) -> str:
    """Assemble the standing instruction for this campaign and player.

    Args:
        context: The campaign settings and character information.

    Returns:
        The complete system prompt: the base instructions, plus the tone,
        length and content settings, plus what the model needs to know about
        this specific story.
    """
    parts = [
        DM_SYSTEM_PROMPT,
        TONE_INSTRUCTIONS.get(context.tone, TONE_INSTRUCTIONS["heroic"]),
        LENGTH_INSTRUCTIONS.get(context.narration_length, LENGTH_INSTRUCTIONS["standard"]),
        FILTER_INSTRUCTIONS.get(context.content_filter, FILTER_INSTRUCTIONS["standard"]),
        f"\nCAMPAIGN: {context.campaign_title}",
    ]
    if context.campaign_premise:
        parts.append(f"PREMISE: {context.campaign_premise}")
    if context.character_summary:
        parts.append(f"THE PLAYER CHARACTER: {context.character_summary}")
    else:
        parts.append(
            "THE PLAYER CHARACTER: not yet created. If this is the first turn, open by "
            "establishing the scene and inviting them to say who they are."
        )
    return "\n".join(parts)


def build_contents(context: TurnContext) -> list[dict[str, object]]:
    """Assemble the conversation in the shape the Gemini API expects.

    Gemini takes a list of turns, each labelled with who spoke. Our stored
    roles are ``player`` and ``dungeon_master``; Gemini's are ``user`` and
    ``model``. This function performs that translation.

    Args:
        context: The turn context, including the recent history.

    Returns:
        The list of conversation turns, ending with what the player just said.
    """
    contents: list[dict[str, object]] = []
    for message in context.history[-HISTORY_WINDOW:]:
        if message.role == "system":
            continue
        role = "user" if message.role == "player" else "model"
        contents.append({"role": role, "parts": [{"text": message.content}]})
    contents.append({"role": "user", "parts": [{"text": context.player_message}]})
    return contents


def opening_scene_prompt(campaign_title: str, premise: str | None, tone: str) -> str:
    """Build the instruction that opens a brand new campaign.

    A new campaign has no player message to respond to, so the model needs
    something to react to instead. This provides it.

    Args:
        campaign_title: The story's name.
        premise: The opening situation, if the player supplied one.
        tone: The campaign's tone.

    Returns:
        A first-turn instruction asking for an opening scene.
    """
    premise_line = premise or "Invent an opening situation that fits the title."
    return (
        f"Open the campaign '{campaign_title}'. {premise_line}\n\n"
        "Set the scene in two or three paragraphs. Establish where the player is, what "
        "they can sense, and one thing that immediately demands their attention. "
        f"Keep to the {tone} tone. End by asking what they do."
    )
