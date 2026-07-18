import { anonymizedFilename } from "@/lib/download";

describe("anonymizedFilename", () => {
  it("replaces the extension and appends the anonymized suffix", () => {
    expect(anonymizedFilename("class_photo.png")).toBe("class_photo_anonymized.jpg");
    expect(anonymizedFilename("spring field day.jpg")).toBe("spring_field_day_anonymized.jpg");
  });

  it("sanitizes unsafe characters", () => {
    expect(anonymizedFilename("weird/..\\name?.jpeg")).toBe("weird_name_anonymized.jpg");
  });

  it("falls back when the name is empty", () => {
    expect(anonymizedFilename("")).toBe("photo_anonymized.jpg");
    expect(anonymizedFilename(".jpg")).toBe("photo_anonymized.jpg");
  });
});
