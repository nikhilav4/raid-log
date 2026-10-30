# raid-log

RAID log as code: keep a project's risks, assumptions, issues and dependencies in a YAML file next
to the code, then check it, report on it, and see what changed since the last steering meeting.

Most RAID logs live in a spreadsheet that drifts. Owners go missing, review dates pass without
anyone noticing, and a risk whose likelihood just went up looks the same as one that hasn't moved.
A steering committee mostly wants two answers: where is the biggest exposure right now, and what
changed since we last met. raid-log answers both from a plain YAML file that can sit in the repo and
go through review like any other change. I keep RAID logs while running Agile delivery for a
healthcare software platform, and they feed the status reporting to leadership.

## Quick start

```bash
git clone https://github.com/nikhilav4/raid-log.git
cd raid-log
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e .

raid validate examples/ehr-integration.yaml --today 2026-10-28
raid report examples/ehr-integration.yaml --today 2026-10-28 --since 2026-10-13
raid diff examples/ehr-integration.yaml --against examples/ehr-integration-2026-10-13.yaml
```

Needs Python 3.11 or newer. The example register is dated October 2026, so `--today` pins the date
and the output matches what is shown below. The project, people and dates in the examples are made
up.

## Commands

| Command | What it is for |
| --- | --- |
| `raid validate` | Checks the register against the format and the RAID rules. Structural problems are errors (exit 1). Date-driven problems, such as an overdue review, are warnings, so a register that was fine when merged does not start failing CI on its own. `--strict` fails on warnings too, and `--format github` prints pull request annotations. |
| `raid report` | Status report in Markdown or standalone HTML: top risks by exposure, what is new and closed since a date, overdue reviews, aging issues and dependencies coming due. |
| `raid heatmap` | 5x5 probability by impact grid with risk IDs in their cells, as PNG or SVG. |
| `raid diff` | What changed since a git ref, a date, or another copy of the register: new, closed, reopened, exposure up and down. |
| `raid add` | Appends an item with the next free ID, keeps the file's comments and layout, and refuses to write an item that would fail validation. `--dry-run` shows the item without writing it. |

## Example output

```
$ raid validate examples/ehr-integration.yaml --today 2026-10-28
examples/ehr-integration.yaml:105: warning R-007: review was due 2026-10-26 (2 days ago) [review-overdue]
examples/ehr-integration.yaml: 22 items, 0 errors, 1 warning
```

```
$ raid diff examples/ehr-integration.yaml --against examples/ehr-integration-2026-10-13.yaml
Changes to EHR Integration Phase 2 since examples/ehr-integration-2026-10-13.yaml

New (4)
  R-006  Interface analyst who knows the mappings best leaves in November
         risk, exposure 9, open, owner Elena Ruiz
  ...

Exposure up (2)
  R-001  Interface vendor may slip the HL7 ADT feed
         exposure 15 -> 20 (probability 3 -> 4)
         status monitoring -> mitigating
         review_by 2026-10-27 -> 2026-11-03
         note 2026-10-24: Test feed slipped to 11-04; probability raised from 3 to 4
  R-003  Night-shift nurses may not finish training before go-live
         exposure 8 -> 12 (probability 2 -> 3)
         mitigation added: Recorded sessions plus super-user rounding on nights for the first two weeks
```

The top of `raid report`:

| ID | Risk | P x I | Exposure | Owner | Status | Review by |
| --- | --- | --- | ---: | --- | --- | --- |
| R-001 | Interface vendor may slip the HL7 ADT feed | 4 x 5 | 20 | Priya Shah | mitigating | 2026-11-03 |
| R-002 | Duplicate patient records in the legacy MPI could overlay charts during the merge | 3 x 5 | 15 | Marcus Bell | mitigating | 2026-11-05 |
| R-003 | Night-shift nurses may not finish training before go-live | 3 x 4 | 12 | Jordan Reyes | open | 2026-11-02 |

## The register format

```yaml
project: EHR Integration Phase 2
updated: 2026-10-27
items:
  - id: R-001
    type: risk            # risk | assumption | issue | dependency
    title: Interface vendor may slip the HL7 ADT feed
    owner: Priya Shah
    status: mitigating    # open | monitoring | mitigating | resolved | closed
    raised: 2026-09-02
    review_by: 2026-11-03
    probability: 4        # 1-5
    impact: 5             # 1-5
    mitigation: Weekly vendor checkpoint; flat-file fallback scoped
    links: [D-001]
```

Exposure is probability times impact, from 1 to 25. An active risk with exposure 12 or more must
have a mitigation. Issues carry a severity, dependencies a counterparty and a need-by date, and
assumptions a validate-by date. Resolved and closed items need a resolution.

## Status

Working now: the five commands above, with tests. In progress: a reusable GitHub Action that lints
the register in pull requests and writes the status report to the job summary, and generated
example reports in `docs/`.

## License

MIT. See [LICENSE](LICENSE).
