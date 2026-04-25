# Word Template Licenses

The three `.docx` templates in this directory were **auto-generated** by the plugin's install pipeline using `python-docx`. They are not derived from any third-party templates.

| Template | Style | License |
|---|---|---|
| `arxiv-shared-1.docx` | Single-column, Times New Roman 11pt, 1" margins | MIT (this plugin) |
| `minimalist.docx` | Single-column, Calibri 11pt, 1.25" margins | MIT (this plugin) |
| `two-column-academic.docx` | Two-column, Times New Roman 10pt, 0.75" margins | MIT (this plugin) |

All three contain placeholder tokens (`%TITLE%`, `%AUTHOR%`, `%ABSTRACT_BODY%`, etc.) that the orchestrator replaces with content from the manuscript-writer agent at Phase 8.25 (Word export).

## Restyling

Open any `.docx` in Microsoft Word or LibreOffice Writer to adjust fonts, colors, headings, and margins. The plugin will use whatever styles you define — placeholders remain functional as long as the token strings (`%TITLE%`, etc.) are preserved.

## Adding a custom template

1. Save your `.docx` with the placeholder tokens listed in this file (any subset works; missing placeholders are skipped).
2. Place it at `mcp/templates/word/<your-name>.docx`.
3. Add `<your-name>` to the `manuscript.word_template` enum in `settings/settings.schema.json`.
4. Reference it via `--word-template <your-name>` or in `~/.claude/settings.json`.
