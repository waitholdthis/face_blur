"use client";

import { useCallback, useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { api, ApiError } from "@/lib/api";
import type { Student } from "@/lib/types";

export default function StudentsPage() {
  const [students, setStudents] = useState<Student[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    student_id_number: "",
    grade_level: "",
  });
  const [files, setFiles] = useState<File[]>([]);

  const load = useCallback(async () => {
    try {
      setStudents(await api.listStudents());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load registry");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (files.length === 0) {
      setError("A reference photo is required to enroll a student.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("first_name", form.first_name);
      fd.append("last_name", form.last_name);
      fd.append("student_id_number", form.student_id_number);
      fd.append("grade_level", form.grade_level);
      fd.append("parent_consent_signed", "false");
      files.forEach((file) => fd.append("reference_images", file));
      await api.createStudent(fd);
      setForm({ first_name: "", last_name: "", student_id_number: "", grade_level: "" });
      setFiles([]);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Enrollment failed");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    try {
      await api.deleteStudent(id);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Delete failed");
    }
  };

  return (
    <AppShell>
      <h1 className="page-title">No-Consent Opt-Out Registry</h1>
      <p className="page-sub">
        Students whose parents did not sign a social-media consent form. Any face matching an
        entry here is automatically flagged for anonymization.
      </p>

      {error && <div className="error" style={{ marginBottom: 16 }}>{error}</div>}

      <div style={{ display: "flex", gap: 20, alignItems: "flex-start", flexWrap: "wrap" }}>
        <div className="card" style={{ flex: "1 1 320px", maxWidth: 380 }}>
          <h3 style={{ marginTop: 0 }}>Enroll student</h3>
          <form onSubmit={submit}>
            <label className="label">First name</label>
            <input
              className="input"
              value={form.first_name}
              onChange={(e) => setForm({ ...form, first_name: e.target.value })}
              required
            />
            <label className="label">Last name</label>
            <input
              className="input"
              value={form.last_name}
              onChange={(e) => setForm({ ...form, last_name: e.target.value })}
              required
            />
            <label className="label">Student ID</label>
            <input
              className="input"
              value={form.student_id_number}
              onChange={(e) => setForm({ ...form, student_id_number: e.target.value })}
              required
            />
            <label className="label">Grade level</label>
            <input
              className="input"
              value={form.grade_level}
              onChange={(e) => setForm({ ...form, grade_level: e.target.value })}
              required
            />
            <label className="label">Reference photos (1–5, one face each)</label>
            <input
              className="input"
              type="file"
              accept="image/*"
              multiple
              onChange={(e) => setFiles(Array.from(e.target.files ?? []).slice(0, 5))}
            />
            <p className="muted" style={{ fontSize: 12, margin: "7px 0 0" }}>
              Add a few clear angles when possible. Blurry, dark, or multi-person photos are rejected.
              {files.length > 0 && ` ${files.length} selected.`}
            </p>
            <button className="btn" style={{ width: "100%", marginTop: 18 }} disabled={busy}>
              {busy ? "Enrolling…" : "Enroll student"}
            </button>
          </form>
        </div>

        <div className="card" style={{ flex: "2 1 480px", padding: 0 }}>
          {students.length === 0 ? (
            <p className="muted" style={{ padding: 20 }}>
              No students enrolled yet.
            </p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Student ID</th>
                  <th>Grade</th>
                  <th>References</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {students.map((s) => (
                  <tr key={s.id}>
                    <td>
                      {s.first_name} {s.last_name}
                    </td>
                    <td>{s.student_id_number}</td>
                    <td>{s.grade_level}</td>
                    <td>{s.reference_count}</td>
                    <td>
                      <button
                        className="btn danger"
                        style={{ padding: "4px 10px", fontSize: 13 }}
                        onClick={() => remove(s.id)}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </AppShell>
  );
}
