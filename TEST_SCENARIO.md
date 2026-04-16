# MCDA Test Scenario — Office Lease Selection

This scenario is the working fixture for building and testing the v1 CLI. It is small
enough to reason about by hand but rich enough to exercise min/max criteria, hierarchy,
participant aggregation, thresholds, reference alternatives, missing-data handling, and
ELECTRE III outranking.

---

## Decision Context

Choose a new office lease for a 35-person software team.

The team is deciding among three candidate offices and one reference option. The reference
is the current office. It should be included for comparison, but it should not be eligible
as the default recommended new lease.

Project ID:

```text
office_lease_selection
```

Project title:

```text
Office lease selection
```

Description:

```text
Select the best office lease for the next three years, balancing total cost, commute
burden, space quality, and lease flexibility. The current office is included as a
reference baseline.
```

Default lambda:

```text
0.75
```

---

## Alternatives

| ID | Name | Type | Description |
| --- | --- | --- | --- |
| `downtown_loft` | Downtown Loft | candidate | Strong transit access and excellent space quality, with high rent. |
| `midtown_suite` | Midtown Suite | candidate | Balanced option with moderate cost, commute, and quality. |
| `suburban_campus` | Suburban Campus | candidate | Lowest rent and most flexible lease, but worse commute. |
| `current_office` | Current Office | reference | Baseline current lease; included for comparison only. |

---

## Participants

| ID | Name | Traits |
| --- | --- | --- |
| `alice` | Alice Rivera | role: `operations`, years_experience: `10` |
| `bob` | Bob Chen | role: `engineering`, years_experience: `7` |
| `carol` | Carol Singh | role: `finance`, years_experience: `12` |

All participants may weight, evaluate, and set thresholds.

---

## Criteria

The criteria use one group so we can test hierarchical weights.

```text
financial
  annual_cost
commute_time
space_quality
lease_flexibility
```

| ID | Name | Direction | Unit | Parent | Description |
| --- | --- | --- | --- | --- | --- |
| `financial` | Financial | group | null | null | Commercial impact of the lease. |
| `annual_cost` | Annual cost | min | thousands USD per year | `financial` | Fully loaded annual lease cost. Lower is better. |
| `commute_time` | Commute time | min | average minutes | null | Estimated average one-way commute for employees. Lower is better. |
| `space_quality` | Space quality | max | score 0-100 | null | Workspace quality, meeting rooms, light, amenities, and layout. Higher is better. |
| `lease_flexibility` | Lease flexibility | max | score 0-100 | null | Ability to expand, exit, sublease, or renegotiate. Higher is better. |

---

## Weights

Participants submit local sibling weights. Root-level siblings are:

```text
financial, commute_time, space_quality, lease_flexibility
```

The `financial` group has one child in this scenario, so `annual_cost` receives local
weight `1.0` within the group. This still exercises group handling without making the
first fixture too large.

### Alice

| Criterion | Raw local weight | Confidence |
| --- | ---: | ---: |
| `financial` | 30 | 0.9 |
| `commute_time` | 25 | 0.8 |
| `space_quality` | 30 | 0.9 |
| `lease_flexibility` | 15 | 0.7 |
| `annual_cost` | 1 | 1.0 |

### Bob

| Criterion | Raw local weight | Confidence |
| --- | ---: | ---: |
| `financial` | 20 | 0.8 |
| `commute_time` | 35 | 0.9 |
| `space_quality` | 30 | 0.8 |
| `lease_flexibility` | 15 | 0.7 |
| `annual_cost` | 1 | 1.0 |

### Carol

| Criterion | Raw local weight | Confidence |
| --- | ---: | ---: |
| `financial` | 40 | 0.95 |
| `commute_time` | 20 | 0.8 |
| `space_quality` | 25 | 0.8 |
| `lease_flexibility` | 15 | 0.8 |
| `annual_cost` | 1 | 1.0 |

Expected median normalized root weights:

| Leaf criterion | Expected global weight |
| --- | ---: |
| `annual_cost` | 0.30 |
| `commute_time` | 0.25 |
| `space_quality` | 0.30 |
| `lease_flexibility` | 0.15 |

These expected weights are useful for an early aggregation unit test.

---

## Thresholds

Use the same thresholds for all participants in the first fixture. This keeps the first
ELECTRE tests focused on formula correctness rather than threshold aggregation.

| Criterion | q | p | v |
| --- | ---: | ---: | ---: |
| `annual_cost` | 25 | 75 | 175 |
| `commute_time` | 3 | 8 | 20 |
| `space_quality` | 5 | 15 | 35 |
| `lease_flexibility` | 5 | 15 | null |

Interpretation examples:

- A cost difference within 25k USD is close enough to be mostly indifferent.
- A commute difference over 20 minutes can veto an otherwise attractive option.
- Lease flexibility has no veto threshold.

---

## Performance Values

Values are intentionally shared by all participants in the first fixture. Later tests can
add participant disagreement, abstentions, and missing data.

| Alternative | annual_cost | commute_time | space_quality | lease_flexibility |
| --- | ---: | ---: | ---: | ---: |
| `downtown_loft` | 620 | 28 | 92 | 55 |
| `midtown_suite` | 500 | 35 | 80 | 70 |
| `suburban_campus` | 390 | 52 | 72 | 88 |
| `current_office` | 540 | 38 | 68 | 45 |

Expected qualitative behavior:

- `downtown_loft` should be strong on commute and quality, weak on cost and flexibility.
- `suburban_campus` should be strong on cost and flexibility, weak on commute.
- `midtown_suite` should often appear as the compromise candidate.
- `current_office` should help explain whether moving is worth it, but should not be
  selected as the default recommendation because it is a reference alternative.

---

## Initial Manual Command Script

This script is the target workflow for the first vertical slice. Exact JSON output can be
locked down as implementation stabilizes.

```text
mcda init office_lease_selection --description "Select the best office lease for the next three years."
cd office_lease_selection

mcda participant add alice "Alice Rivera"
mcda participant add bob "Bob Chen"
mcda participant add carol "Carol Singh"

mcda participant set-trait alice role '"operations"'
mcda participant set-trait alice years_experience 10
mcda participant set-trait bob role '"engineering"'
mcda participant set-trait bob years_experience 7
mcda participant set-trait carol role '"finance"'
mcda participant set-trait carol years_experience 12

mcda alt add downtown_loft "Downtown Loft" --type candidate
mcda alt add midtown_suite "Midtown Suite" --type candidate
mcda alt add suburban_campus "Suburban Campus" --type candidate
mcda alt add current_office "Current Office" --type reference

mcda crit add-group financial "Financial"
mcda crit add annual_cost "Annual cost" --direction min --unit "thousands USD per year" --parent financial
mcda crit add commute_time "Commute time" --direction min --unit "average minutes"
mcda crit add space_quality "Space quality" --direction max --unit "score 0-100"
mcda crit add lease_flexibility "Lease flexibility" --direction max --unit "score 0-100"

mcda weights set alice financial 30 --confidence 0.9
mcda weights set alice commute_time 25 --confidence 0.8
mcda weights set alice space_quality 30 --confidence 0.9
mcda weights set alice lease_flexibility 15 --confidence 0.7
mcda weights set alice annual_cost 1 --confidence 1.0

mcda weights set bob financial 20 --confidence 0.8
mcda weights set bob commute_time 35 --confidence 0.9
mcda weights set bob space_quality 30 --confidence 0.8
mcda weights set bob lease_flexibility 15 --confidence 0.7
mcda weights set bob annual_cost 1 --confidence 1.0

mcda weights set carol financial 40 --confidence 0.95
mcda weights set carol commute_time 20 --confidence 0.8
mcda weights set carol space_quality 25 --confidence 0.8
mcda weights set carol lease_flexibility 15 --confidence 0.8
mcda weights set carol annual_cost 1 --confidence 1.0

mcda thresholds set alice annual_cost --q 25 --p 75 --v 175
mcda thresholds set alice commute_time --q 3 --p 8 --v 20
mcda thresholds set alice space_quality --q 5 --p 15 --v 35
mcda thresholds set alice lease_flexibility --q 5 --p 15 --no-veto

mcda thresholds set bob annual_cost --q 25 --p 75 --v 175
mcda thresholds set bob commute_time --q 3 --p 8 --v 20
mcda thresholds set bob space_quality --q 5 --p 15 --v 35
mcda thresholds set bob lease_flexibility --q 5 --p 15 --no-veto

mcda thresholds set carol annual_cost --q 25 --p 75 --v 175
mcda thresholds set carol commute_time --q 3 --p 8 --v 20
mcda thresholds set carol space_quality --q 5 --p 15 --v 35
mcda thresholds set carol lease_flexibility --q 5 --p 15 --no-veto
```

Performance entry commands are repetitive. For implementation tests, it is acceptable to
load the values above through a fixture helper or `mcda perf import` once import exists.

---

## Early Test Assertions

Use these checks while building:

1. `mcda init office_lease_selection` creates `office_lease_selection/.mcda/`.
2. No command writes generated MCDA files outside `.mcda/`.
3. Project discovery works from the project root and from a nested subdirectory.
4. IDs reject hyphenated values such as `downtown-loft`.
5. Append-style records use microsecond UTC timestamp plus UUID suffix.
6. Median normalized weights resolve to:
   - `annual_cost = 0.30`
   - `commute_time = 0.25`
   - `space_quality = 0.30`
   - `lease_flexibility = 0.15`
7. Reference alternative `current_office` appears in matrices but not in default
   `candidate_ranking`.
8. `--human` changes presentation only; underlying calculations and stored files are the
   same as default JSON mode.
