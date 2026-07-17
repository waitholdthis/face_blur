import { evaluateFinalBlur } from "@/lib/blur";

describe("evaluateFinalBlur (XOR of system + override)", () => {
  const cases: Array<[boolean, boolean, boolean]> = [
    [false, false, false], // clear
    [true, false, true], // system-flagged, kept -> blurred
    [true, true, false], // system-flagged, overridden -> false positive corrected
    [false, true, true], // not flagged, overridden -> false negative corrected
  ];

  it.each(cases)(
    "system=%s override=%s -> %s",
    (is_blurred_by_system, is_blurred_override, expected) => {
      expect(
        evaluateFinalBlur({ is_blurred_by_system, is_blurred_override })
      ).toBe(expected);
    }
  );
});
