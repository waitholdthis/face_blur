import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import UploadPage from "@/app/upload/page";

const mockPush = jest.fn();
const mockUploadMediaBatch = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock("@/components/AppShell", () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => children,
}));

jest.mock("@/lib/api", () => ({
  api: {
    uploadMediaBatch: (...args: unknown[]) => mockUploadMediaBatch(...args),
  },
  ApiError: class ApiError extends Error {},
}));

describe("UploadPage", () => {
  beforeEach(() => {
    mockPush.mockReset();
    mockUploadMediaBatch.mockReset().mockResolvedValue({ uploaded_count: 2 });
  });

  it("submits multiple selected photos in one batch", async () => {
    render(<UploadPage />);
    const first = new File(["first"], "first.jpg", { type: "image/jpeg" });
    const second = new File(["second"], "second.png", { type: "image/png" });
    const input = screen.getByLabelText("Image files (JPEG / PNG)");
    fireEvent.change(input, { target: { files: [first, second] } });

    expect(screen.getByText("2 photos selected")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Upload and process 2 photos"));

    await waitFor(() => expect(mockUploadMediaBatch).toHaveBeenCalledTimes(1));
    const form = mockUploadMediaBatch.mock.calls[0][0] as FormData;
    expect(form.getAll("files")).toHaveLength(2);
    expect(mockPush).toHaveBeenCalledWith("/dashboard");
  });
});
