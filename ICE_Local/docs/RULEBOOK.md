# The routing rulebook

All imported articles stay in the **General** queue (`REGULAR`). The rulebook below still checks metadata against source evidence and records matching findings for review; it does not route articles to another queue. Matching rules live in one text file:

```
ICE_Local/config/rulebook.toml
```

A fired rule is recorded as a matching finding on the article. The article remains in General whether checks pass, findings need review, sources are incomplete, or the rulebook has an error. These results must not be read as approval.

## Editing the rulebook

Open the file in Notepad or any text editor, change it, and save it as UTF-8. Each rule is a block like this:

```toml
[author_name_extras]
on = true
group = "Authors"
text = "An API or PDF author has an alternate name, nickname (alias), suffix, degree or honorific."
honorifics = ["Dr", "Prof", "Professor", "Mr", "Mrs", "Ms", "Miss", "Sir", "Dame", "Rev", "Revd"]
```

- `on = true` or `on = false` turns the rule on or off.
- `text` is the reason shown on the article when the rule fires.
- `group` is the heading the rule is listed under in the app.
- Any other line is a setting for that rule. Word lists go in square brackets, each word in double quotes, separated by commas.
- Lines starting with `#` are notes and are ignored.

**When changes apply.** ICE reads the file during each article match, so the next upload uses your change without a restart. Choose **Match & regenerate XML** to re-run matching on imported articles, regenerate generated XML, and retry failed imports. Directly edited XML is preserved.

**Mistakes are never silent.** A misspelt rule name or setting, a wrong kind of value (for example text where a number belongs), or broken syntax is an error. The Rules dialog shows it in red, the console window prints it at startup, and every article stays in General and shows the reason "Rulebook error: …" until the file is fixed. A rule left out of the file counts as off and is listed as "Off · not in file".

**What a text edit can and can't do.** The rule names in `[brackets]` are fixed: each is a check built into ICE (`ICE_Local/rulebook.py`). Editing the file can switch any of them on or off and change their wording, word lists and numbers. It can't create a new kind of check from a sentence, because ICE never interprets English rules at runtime. A new kind of check needs a developer to add it once (see the end of this page); after that it is switched from this file like the others.

To try a different rulebook without editing the shipped one, set the `ICE_RULEBOOK` environment variable to its path before starting ICE.

## Review notes (always on)

These apply whatever the rulebook says:

- the PDF, API, Scrapping or HTML file is missing, or a support file can't be read;
- the generated XML fails validation;
- the XML was edited by hand and hasn't been reconciled with the sources;
- the rulebook itself has an error.

All rulebook and extraction findings are review notes. ICE has no HOLD state; findings do not block XML generation, metadata saving or export. A corrupt or missing source can still prevent extraction because there is no usable PDF to read.

## The rules

| Rule | Fires when | Settings |
|---|---|---|
| `id_missing` | No arXiv ID is printed in the PDF. | – |
| `id_version_mismatch` | The PDF ID or version differs from a listed source, or that source's ID can't be read. `arXiv:` prefixes and `v1` suffixes are ignored. The HTML version is only compared when the page shows one version. | `compare_with` (`"SCRAPPING"`, `"HTML"`, `"API"`) |
| `title_mismatch` | The PDF title and the HTML title differ in letters or digits. Case, accents, punctuation, dashes, spacing and markup are ignored. | `compare_with` |
| `abstract_missing` | No abstract was found. With `require_heading = true`, an abstract without a printed "Abstract" heading also counts. | `require_heading` |
| `abstract_is_pitch` | An "Elevator pitch" or "Teaser" heading is printed on the first pages and there is no Abstract heading, or the captured abstract runs into that section. | `headings`, `pages` |
| `author_mismatch` | The PDF and API authors differ in number, order or name content; an API author isn't in the PDF; or the PDF author line has names the API doesn't list. Honorifics, suffixes and degrees from `author_name_extras` are ignored here. | `initials_match_full_names` |
| `author_affiliation_unlinked` | An author has no printed indicator matching an affiliation, is linked only because one unmarked affiliation sits near the authors, or has an indicator with no affiliation; or an affiliation has no author. | `allow_single_author_single_affiliation` |
| `author_name_extras` | An API or PDF name has an honorific before it, a suffix or degree after it, or an alias (brackets, quotes, or a word such as "née"). | `honorifics`, `suffixes`, `degrees`, `alias_words` |
| `references_two_locations` | References are printed in two or more places: separate numbered runs, more than one reference heading with entries, or dated footnote citations beside the main list. | – |
| `references_missing` | No references were captured. | – |
| `references_incomplete` | An entry is shorter than `min_length` characters, ends with `, ; :`, `...` or a bare `doi:`/`arXiv:`, or holds an underscore placeholder. Also fires when the printed numbering has gaps, or the PDF prints more reference numbers than were captured. | `min_length` |
| `references_multiple` | One entry looks like it holds more than one work (a second dated work after `;`, or a "cf."/"see" pointer). | – |
| `reference_hyperlinks` | A clickable link overlaps a reference, or (with `include_printed_addresses`) a reference prints a web or DOI address. | `include_printed_addresses` |
| `correspondence_address` | On the first `pages` pages, a line starts with one of the `phrases` and it, or the line under it, holds an address (organization, street, country or postcode). An email address alone doesn't count. | `phrases`, `pages` |
| `affiliation_outside_front` | An affiliation-like block is found past page 1 (mid-paper, in a page footer, or after the references) and hasn't been dismissed, or a biography heading is printed. | `biography_headings` |
| `affiliation_non_english` | An affiliation contains one of the `words`, or (with `non_latin_script`) is written in a non-Latin script. | `words`, `non_latin_script` |
| `orcid` | The PDF links to orcid.org, prints "ORCID" or an ORCID iD, or an author has an ORCID recorded. | – |

## Known limits

- An ORCID logo that is only an image, with no link and no printed text, can't be seen.
- `author_mismatch` finds extra PDF authors only on the lines where API authors were found. An extra author on a separate line is missed.
- Alias, multiple-work and incomplete-reference detection are pattern checks. They catch the common forms, not every one.
- Affiliations inside ordinary body text, with no marker and no footer position, aren't detected as mid-paper affiliations.

## Adding a new kind of check (developers)

1. In `rulebook.py`, add a function decorated with `@rule('key', 'Group', 'Default reason text', **default_settings)`. It receives `ctx` (`ctx.md` is the metadata, `ctx.layout` is the PDF extraction, `ctx.s` is the rule's settings). It returns `None` when nothing is found, or `(detail, evidence)` when the rule fires.
2. Add a `[key]` block to `config/rulebook.toml`.
3. In `tests/test_rulebook.py`, add a case where the rule fires and one where it doesn't.
4. Run `python -m unittest discover -s tests -v`.
