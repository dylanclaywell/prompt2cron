"""prompt2cron desktop app.

A CustomTkinter UI with two complementary directions:

  forward:  plain English  --(Claude)-->  cron expression
  reverse:  cron expression --(cron-descriptor)--> plain English

The reverse description updates live as the cron field changes, so the user can
verify Claude's output, hand-edit it, or type their own schedule from scratch
and immediately see what it means.
"""

from __future__ import annotations

import threading

import customtkinter as ctk
from cron_descriptor import Options, ExpressionDescriptor

from . import config
from .claude_client import CronConversionError, natural_language_to_cron

MONO = ("Cascadia Code", "Consolas", "monospace")

ERROR_COLOR = ("#c0392b", "#ff6b6b")
MUTED_COLOR = ("gray45", "gray60")
BODY_COLOR = ("gray10", "gray90")


class AutoHideScrollableFrame(ctk.CTkScrollableFrame):
    """A scrollable frame whose scrollbar only appears when content overflows."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Re-route the canvas scroll callback through our own so we can show or
        # hide the scrollbar based on whether the whole view fits.
        self._parent_canvas.configure(yscrollcommand=self._on_scroll)

    def _on_scroll(self, first: str, last: str) -> None:
        self._scrollbar.set(first, last)
        if float(first) <= 0.0 and float(last) >= 1.0:
            self._scrollbar.grid_remove()
        else:
            self._scrollbar.grid()


class SettingsDialog(ctk.CTkToplevel):
    """Modal dialog to view, save, or clear the stored Anthropic API key."""

    def __init__(self, parent: "App") -> None:
        super().__init__(parent)
        self._parent = parent

        self.title("Settings — Anthropic API Key")
        self.geometry("480x270")
        self.resizable(False, False)
        self.transient(parent)

        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text="Anthropic API Key",
            font=ctk.CTkFont(size=17, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=24, pady=(22, 2))

        ctk.CTkLabel(
            self,
            text="Stored securely in your system keychain. Takes precedence "
            "over the ANTHROPIC_API_KEY environment variable.",
            text_color=MUTED_COLOR,
            font=ctk.CTkFont(size=11),
            wraplength=430,
            justify="left",
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 14))

        self.key_var = ctk.StringVar(value=config.get_stored_key() or "")
        self.key_entry = ctk.CTkEntry(
            self,
            textvariable=self.key_var,
            show="•",
            height=38,
            placeholder_text="sk-ant-…",
        )
        self.key_entry.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 6))

        self.show_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            self,
            text="Show key",
            variable=self.show_var,
            command=self._toggle_show,
            checkbox_width=18,
            checkbox_height=18,
            font=ctk.CTkFont(size=12),
        ).grid(row=3, column=0, sticky="w", padx=24, pady=(0, 16))

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 8))
        buttons.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            buttons, text="Clear", width=92, fg_color="transparent",
            border_width=1, text_color=BODY_COLOR, command=self._clear,
        ).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(
            buttons, text="Cancel", width=92, fg_color="transparent",
            border_width=1, text_color=BODY_COLOR, command=self.destroy,
        ).grid(row=0, column=2, padx=(0, 8))
        ctk.CTkButton(buttons, text="Save", width=92, command=self._save).grid(
            row=0, column=3
        )

        self.status = ctk.CTkLabel(
            self, text="", text_color=MUTED_COLOR,
            font=ctk.CTkFont(size=11), anchor="w",
        )
        self.status.grid(row=5, column=0, sticky="ew", padx=24, pady=(0, 8))

        self.after(50, self.key_entry.focus_set)

    def _toggle_show(self) -> None:
        self.key_entry.configure(show="" if self.show_var.get() else "•")

    def _save(self) -> None:
        key = self.key_var.get().strip()
        if not key:
            self.status.configure(
                text="Enter a key, or use Clear to remove the saved one.",
                text_color=ERROR_COLOR,
            )
            return
        try:
            config.save_api_key(key)
        except config.KeyStoreError as exc:
            self.status.configure(text=str(exc), text_color=ERROR_COLOR)
            return
        self._parent._show_key_hint()
        self.destroy()

    def _clear(self) -> None:
        config.clear_api_key()
        self.key_var.set("")
        self._parent._show_key_hint()
        self.status.configure(text="Saved key cleared.", text_color=MUTED_COLOR)


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title("prompt2cron")
        self.geometry("660x620")
        self.minsize(560, 560)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.cron_var = ctk.StringVar()
        self.cron_var.trace_add("write", self._on_cron_changed)

        self._build_toolbar()
        self._build_body()
        self._show_key_hint()

    # ---- toolbar --------------------------------------------------------

    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(self, height=56, corner_radius=0,
                           fg_color=("gray88", "gray14"))
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_columnconfigure(1, weight=1)
        bar.grid_propagate(False)

        ctk.CTkLabel(
            bar, text="⏱  prompt2cron",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=20, pady=12)

        controls = ctk.CTkFrame(bar, fg_color="transparent")
        controls.grid(row=0, column=2, sticky="e", padx=16)

        self.appearance = ctk.CTkSegmentedButton(
            controls, values=["Light", "Dark", "System"],
            command=self._set_appearance, width=200,
            font=ctk.CTkFont(size=12),
        )
        self.appearance.set("Dark")
        self.appearance.grid(row=0, column=0, padx=(0, 12))

        ctk.CTkButton(
            controls, text="⚙  API Key", width=96,
            fg_color="transparent", border_width=1, text_color=BODY_COLOR,
            command=self._open_settings,
        ).grid(row=0, column=1)

    def _set_appearance(self, value: str) -> None:
        ctk.set_appearance_mode(value.lower())

    def _open_settings(self) -> None:
        SettingsDialog(self).grab_set()

    def _show_key_hint(self) -> None:
        source = config.key_source()
        if source == "keyring":
            self._set_status("Using the API key from your system keychain.")
        elif source == "env":
            self._set_status("Using the API key from ANTHROPIC_API_KEY.")
        else:
            self._set_status(
                "No API key set — add one with the ⚙ API Key button.",
                error=True,
            )

    # ---- body -----------------------------------------------------------

    def _build_body(self) -> None:
        body = AutoHideScrollableFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=20, pady=16)
        body.grid_columnconfigure(0, weight=1)

        # --- input card ---
        in_card = ctk.CTkFrame(body, corner_radius=14)
        in_card.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        in_card.grid_columnconfigure(0, weight=1)

        self._card_heading(in_card, "Describe a schedule").grid(
            row=0, column=0, sticky="w", padx=18, pady=(16, 0)
        )
        ctk.CTkLabel(
            in_card, text="Plain English — Claude turns it into cron.",
            text_color=MUTED_COLOR, font=ctk.CTkFont(size=12), anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))

        self.prompt_entry = ctk.CTkTextbox(
            in_card, height=72, wrap="word", corner_radius=10,
            font=ctk.CTkFont(size=14),
        )
        self.prompt_entry.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 12))
        self.prompt_entry.bind("<Control-Return>", lambda e: self._convert())

        self.convert_btn = ctk.CTkButton(
            in_card, text="Convert to cron  ↓", height=40,
            font=ctk.CTkFont(size=14, weight="bold"), command=self._convert,
        )
        self.convert_btn.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 18))

        # --- output card ---
        out_card = ctk.CTkFrame(body, corner_radius=14)
        out_card.grid(row=1, column=0, sticky="ew")
        out_card.grid_columnconfigure(0, weight=1)

        self._card_heading(out_card, "Cron expression").grid(
            row=0, column=0, sticky="w", padx=18, pady=(16, 10)
        )

        entry_row = ctk.CTkFrame(out_card, fg_color="transparent")
        entry_row.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 4))
        entry_row.grid_columnconfigure(0, weight=1)

        self.cron_entry = ctk.CTkEntry(
            entry_row, textvariable=self.cron_var, height=44,
            font=ctk.CTkFont(family=MONO[0], size=18),
            placeholder_text="* * * * *", justify="center",
        )
        self.cron_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.copy_btn = ctk.CTkButton(
            entry_row, text="Copy", width=70, height=44,
            fg_color="transparent", border_width=1, text_color=BODY_COLOR,
            command=self._copy_cron,
        )
        self.copy_btn.grid(row=0, column=1)

        ctk.CTkLabel(
            out_card,
            text="Edit freely — the description below updates as you type.",
            text_color=MUTED_COLOR, font=ctk.CTkFont(size=11), anchor="w",
        ).grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 14))

        ctk.CTkFrame(out_card, height=1, fg_color=("gray80", "gray25")).grid(
            row=3, column=0, sticky="ew", padx=18
        )

        ctk.CTkLabel(
            out_card, text="WHAT IT MEANS", text_color=MUTED_COLOR,
            font=ctk.CTkFont(size=11, weight="bold"), anchor="w",
        ).grid(row=4, column=0, sticky="w", padx=18, pady=(14, 2))

        self.description_label = ctk.CTkLabel(
            out_card, text="—", font=ctk.CTkFont(size=16),
            wraplength=560, justify="left", anchor="w",
        )
        self.description_label.grid(row=5, column=0, sticky="ew", padx=18, pady=(0, 18))

        # --- status line ---
        self.status_label = ctk.CTkLabel(
            self, text="", text_color=MUTED_COLOR,
            wraplength=600, justify="left", anchor="w",
            font=ctk.CTkFont(size=12),
        )
        self.status_label.grid(row=2, column=0, sticky="ew", padx=22, pady=(0, 14))

        self.bind("<Configure>", self._on_resize)

    def _card_heading(self, parent: ctk.CTkBaseClass, text: str) -> ctk.CTkLabel:
        return ctk.CTkLabel(
            parent, text=text, font=ctk.CTkFont(size=15, weight="bold"), anchor="w"
        )

    def _on_resize(self, event: object) -> None:
        width = max(320, self.winfo_width() - 120)
        self.description_label.configure(wraplength=width)
        self.status_label.configure(wraplength=width)

    def _copy_cron(self) -> None:
        text = self.cron_var.get().strip()
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.copy_btn.configure(text="Copied!")
        self.after(1200, lambda: self.copy_btn.configure(text="Copy"))

    # ---- forward: English -> cron --------------------------------------

    def _convert(self) -> "str | None":
        prompt = self.prompt_entry.get("1.0", "end").strip()
        if not prompt:
            self._set_status("Type a schedule in plain English first.", error=True)
            return "break"

        self.convert_btn.configure(state="disabled", text="Converting…")
        self._set_status("Asking Claude…")

        threading.Thread(target=self._convert_worker, args=(prompt,), daemon=True).start()
        return "break"  # stop the bound key event from also inserting a newline

    def _convert_worker(self, prompt: str) -> None:
        try:
            result = natural_language_to_cron(prompt)
        except CronConversionError as exc:
            self.after(0, self._convert_failed, str(exc))
        except Exception as exc:  # noqa: BLE001 - surface anything unexpected to the user
            self.after(0, self._convert_failed, f"Unexpected error: {exc}")
        else:
            self.after(0, self._convert_succeeded, result.cron, result.explanation)

    def _convert_succeeded(self, cron: str, explanation: str) -> None:
        self.cron_var.set(cron.strip())  # triggers _on_cron_changed
        self._set_status(explanation)
        self._reset_convert_button()

    def _convert_failed(self, message: str) -> None:
        self._set_status(message, error=True)
        self._reset_convert_button()

    def _reset_convert_button(self) -> None:
        self.convert_btn.configure(state="normal", text="Convert to cron  ↓")

    # ---- reverse: cron -> English --------------------------------------

    def _on_cron_changed(self, *_args: object) -> None:
        expression = self.cron_var.get().strip()
        if not expression:
            self.description_label.configure(text="—", text_color=MUTED_COLOR)
            return

        try:
            options = Options()
            options.throw_exception_on_parse_error = True
            description = ExpressionDescriptor(expression, options).get_description()
        except Exception:  # noqa: BLE001 - cron-descriptor raises several types
            self.description_label.configure(
                text="Not a valid cron expression yet…", text_color=ERROR_COLOR
            )
            return

        self.description_label.configure(text=description, text_color=BODY_COLOR)

    # ---- helpers --------------------------------------------------------

    def _set_status(self, message: str, *, error: bool = False) -> None:
        self.status_label.configure(
            text=message, text_color=ERROR_COLOR if error else MUTED_COLOR
        )


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
