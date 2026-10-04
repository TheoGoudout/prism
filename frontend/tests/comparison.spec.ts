// Unit tests for the period comparison maths: no page involved.
import { expect, test } from "@playwright/test"
import type { PlatformFollowers, TimeSeriesPoint } from "../src/client"
import {
  compareKpi,
  comparisonBasis,
  followersProjector,
  formatChange,
  monthBefore,
  previousPeriod,
  projectCount,
  projectTotals,
  trendRows,
  yearBefore,
} from "../src/lib/comparison"

const NOW = "2026-10-10"

const point = (date: string, engagements: number): TimeSeriesPoint => ({
  date,
  engagements,
})

test.describe("comparison basis", () => {
  test("periods of the same length compare totals", () => {
    expect(
      comparisonBasis(
        { from: "2026-10-01", to: "2026-10-05" },
        { from: "2026-09-01", to: "2026-09-05" },
        NOW,
      ),
    ).toEqual({ kind: "total" })
  })

  test("an open-ended, shorter main period is projected", () => {
    expect(
      comparisonBasis(
        { from: "2026-10-01" },
        { from: "2026-09-01", to: "2026-09-30" },
        NOW,
      ),
    ).toEqual({
      kind: "projected",
      length: 30,
      completeDays: 9, // today, Oct 10, is left out
      end: "2026-10-30",
    })
  })

  test("too few complete days to project: compare per day", () => {
    expect(
      comparisonBasis(
        { from: "2026-10-08" },
        { from: "2026-09-01", to: "2026-09-30" },
        NOW,
      ),
    ).toEqual({ kind: "perDay", tooEarly: true })
  })

  test("closed periods of different lengths compare per day", () => {
    expect(
      comparisonBasis(
        { from: "2026-10-01", to: "2026-10-05" },
        { from: "2026-09-01", to: "2026-09-30" },
        NOW,
      ),
    ).toEqual({ kind: "perDay", tooEarly: false })
  })
})

test.describe("presets", () => {
  test("previous period of an open-ended period", () => {
    expect(previousPeriod({ from: "2026-10-01" }, NOW)).toEqual({
      from: "2026-09-21",
      to: "2026-09-30",
    })
  })

  test("previous month", () => {
    expect(monthBefore("2026-03-15")).toEqual({
      from: "2026-02-01",
      to: "2026-02-28",
    })
  })

  test("same period last year", () => {
    expect(yearBefore({ from: "2028-02-29", to: "2028-03-01" }, NOW)).toEqual({
      from: "2027-02-28",
      to: "2027-03-01",
    })
  })
})

test.describe("projection", () => {
  test("counts continue at their daily rate", () => {
    expect(projectCount([10, 20, 30, 999], 3, 30)).toBe(600)
  })

  test("followers follow each platform's trend from its latest count", () => {
    const series: PlatformFollowers[] = [
      {
        platform: "instagram",
        points: [
          { date: "2026-10-01", followers: 100 },
          { date: "2026-10-02", followers: 110 },
          { date: "2026-10-03", followers: 120 },
        ],
      },
      // Synced from the third day only: no slope, no jump
      {
        platform: "facebook",
        points: [{ date: "2026-10-03", followers: 50 }],
      },
    ]
    const project = followersProjector(series, "2026-10-01", 3)!
    expect(project(2)).toBe(170)
    expect(project(9)).toBe(240)
    expect(followersProjector([], "2026-10-01", 3)).toBeNull()
  })

  test("projected totals", () => {
    const points = [
      point("2026-10-01", 10),
      point("2026-10-02", 20),
      point("2026-10-03", 30),
    ]
    const followers: PlatformFollowers[] = [
      {
        platform: "instagram",
        points: [
          { date: "2026-10-01", followers: 100 },
          { date: "2026-10-03", followers: 104 },
        ],
      },
    ]
    const projections = projectTotals(points, followers, "2026-10-01", {
      kind: "projected",
      length: 10,
      completeDays: 3,
      end: "2026-10-10",
    })
    expect(projections.engagements).toBe(200)
    expect(projections.followers_count).toBe(118)
    expect(projections.followers_growth).toBe(18)
  })
})

test.describe("KPI comparison", () => {
  const context = {
    main: { engagements: 300, engagement_rate: 0.05, followers_count: 1000 },
    compare: { engagements: 400, engagement_rate: 0.04, followers_count: 900 },
    projections: {},
    mainLength: 10,
    compareLength: 20,
  }

  test("per day when the lengths differ", () => {
    const result = compareKpi("engagements", {
      ...context,
      basis: { kind: "perDay", tooEarly: false },
    })
    expect(result).toMatchObject({ current: 30, previous: 20, perDay: true })
    expect(result.change).toBeCloseTo(0.5)
  })

  test("rates in points, levels as they are", () => {
    const basis = { kind: "perDay", tooEarly: false } as const
    const rate = compareKpi("engagement_rate", { ...context, basis })
    expect(rate.kind).toBe("points")
    expect(rate.change).toBeCloseTo(0.01)
    expect(compareKpi("followers_count", { ...context, basis })).toMatchObject({
      change: 100,
      perDay: false,
    })
  })

  test("projected figures replace the totals", () => {
    const result = compareKpi("engagements", {
      ...context,
      basis: { kind: "projected", length: 20, completeDays: 9, end: NOW },
      projections: { engagements: 600 },
    })
    expect(result).toMatchObject({ current: 600, change: 0.5, projected: true })
  })

  test("no change against nothing", () => {
    const result = compareKpi("engagements", {
      ...context,
      compare: { engagements: 0 },
      basis: { kind: "total" },
    })
    expect(result.change).toBeNull()
    expect(formatChange(result.change, result.kind)).toBe("—")
  })

  test("formatting", () => {
    expect(formatChange(0.1234, "relative")).toBe("+12.3%")
    expect(formatChange(-0.0042, "points")).toBe("-0.42 pts")
    expect(formatChange(1234, "absolute")).toBe("+1.2K")
    expect(formatChange(3.44, "absolute")).toBe("+3.4")
  })
})

test("the cumulative projection continues the main line", () => {
  const rows = trendRows({
    metric: "engagements",
    cumulative: true,
    main: { from: "2026-10-07" },
    mainPoints: [
      point("2026-10-07", 10),
      point("2026-10-08", 20),
      point("2026-10-09", 30),
      point("2026-10-10", 1),
    ],
    mainFollowers: [],
    compare: { from: "2026-09-01", to: "2026-09-06" },
    comparePoints: [point("2026-09-01", 5)],
    compareFollowers: [],
    basis: comparisonBasis(
      { from: "2026-10-07" },
      { from: "2026-09-01", to: "2026-09-06" },
      NOW,
    ),
    now: NOW,
  })
  expect(rows).toHaveLength(6)
  expect(rows.map((row) => row.main)).toEqual([10, 30, 60, 61, null, null])
  expect(rows.map((row) => row.projected)).toEqual([
    null,
    null,
    60,
    80,
    100,
    120,
  ])
  expect(rows.map((row) => row.compare)).toEqual([5, 5, 5, 5, 5, 5])
  expect(rows[0].compareDate).toBe("2026-09-01")
})
