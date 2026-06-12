"""Claude-backed natural-language -> crontab conversion.

Uses the Anthropic SDK with structured outputs so the model returns a clean,
parseable cron expression instead of prose we'd have to scrape.
"""

from __future__ import annotations

import anthropic
from pydantic import BaseModel, Field

from . import config

# Cheapest tier; the alias (no date suffix) auto-tracks the current Haiku
# snapshot, so this keeps working as versions roll over.
MODEL = "claude-haiku-4-5"

SYSTEM_PROMPT = """\
You convert a user's plain-English scheduling request into a single standard \
5-field cron expression.

The five fields, in order, are:
  minute (0-59) hour (0-23) day-of-month (1-31) month (1-12) day-of-week (0-6, Sunday=0)

Rules:
- Output a standard 5-field expression only. Do NOT include a seconds field or \
a command — just the schedule.
- Use `*`, ranges (`1-5`), lists (`1,3,5`), and steps (`*/15`) as appropriate.
- Interpret times in 24-hour terms (e.g. "9am" -> hour 9, "9pm" -> hour 21).
- If the request is ambiguous, choose the most common-sense interpretation and \
note the assumption briefly in the explanation.
- If the request cannot be expressed as a cron schedule at all, return the cron \
field as an empty string and explain why.
"""


class CronResult(BaseModel):
    """Structured result returned by the model."""

    cron: str = Field(
        description="A standard 5-field cron expression, or an empty string if "
        "the request cannot be expressed as one."
    )
    explanation: str = Field(
        description="A one-sentence note about the interpretation or any "
        "assumptions made."
    )


class CronConversionError(Exception):
    """Raised when the conversion could not be completed."""


def natural_language_to_cron(prompt: str, *, client: anthropic.Anthropic | None = None) -> CronResult:
    """Convert a natural-language schedule into a cron expression via Claude.

    Resolves the API key from the saved config or the ANTHROPIC_API_KEY
    environment variable unless a client is provided. Raises
    CronConversionError with a user-friendly message on failure.
    """
    prompt = prompt.strip()
    if not prompt:
        raise CronConversionError("Enter a schedule in plain English first.")

    if client is None:
        api_key = config.get_api_key()
        if not api_key:
            raise CronConversionError(
                "No Anthropic API key set. Add one via Settings → Anthropic API Key…"
            )
        client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.parse(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            output_format=CronResult,
        )
    except anthropic.AuthenticationError as exc:
        raise CronConversionError(
            "Authentication failed. Set the ANTHROPIC_API_KEY environment "
            "variable to a valid key."
        ) from exc
    except anthropic.APIConnectionError as exc:
        raise CronConversionError(
            "Could not reach the Anthropic API. Check your internet connection."
        ) from exc
    except anthropic.APIStatusError as exc:
        raise CronConversionError(f"API error ({exc.status_code}): {exc.message}") from exc

    if response.stop_reason == "refusal":
        raise CronConversionError("The request was declined by the model's safety system.")

    result = response.parsed_output
    if result is None:
        raise CronConversionError("The model did not return a usable result. Try rephrasing.")

    if not result.cron.strip():
        raise CronConversionError(
            result.explanation or "That request can't be expressed as a cron schedule."
        )

    return result
