"use client";
import * as tus from "tus-js-client";
import { supabaseBrowser } from "@/lib/supabase/client";

const BUCKET = "longform";

/**
 * Resumable (TUS) upload straight to Supabase Storage. Storage RLS limits users to
 * their own `<uid>/uploads|footage|music/` folders, so the key is built here from the
 * session user and a random name — never from the original filename.
 */
export async function uploadFile(
  file: File,
  folder: "uploads" | "footage" | "music",
  onProgress?: (fraction: number) => void,
): Promise<string> {
  const supabase = supabaseBrowser();
  const { data } = await supabase.auth.getSession();
  const session = data.session;
  if (!session) throw new Error("Sign in again to upload.");
  const ext = (file.name.split(".").pop() || "bin").toLowerCase().replace(/[^a-z0-9]/g, "").slice(0, 5);
  const key = `${session.user.id}/${folder}/${crypto.randomUUID()}.${ext}`;
  const endpoint = `${process.env.NEXT_PUBLIC_SUPABASE_URL}/storage/v1/upload/resumable`;

  await new Promise<void>((resolve, reject) => {
    const upload = new tus.Upload(file, {
      endpoint,
      retryDelays: [0, 2000, 5000, 10000, 20000],
      headers: { authorization: `Bearer ${session.access_token}`, "x-upsert": "false" },
      uploadDataDuringCreation: true,
      removeFingerprintOnSuccess: true,
      metadata: { bucketName: BUCKET, objectName: key, contentType: file.type || "application/octet-stream" },
      chunkSize: 6 * 1024 * 1024, // Supabase requires exactly 6 MB chunks
      onError: (err) => reject(err),
      onProgress: (sent, total) => onProgress?.(total ? sent / total : 0),
      onSuccess: () => resolve(),
    });
    upload.findPreviousUploads().then((prev) => {
      if (prev.length) upload.resumeFromPreviousUpload(prev[0]);
      upload.start();
    });
  });
  return key;
}

export async function mediaDuration(file: File): Promise<number> {
  const url = URL.createObjectURL(file);
  try {
    return await new Promise<number>((resolve, reject) => {
      const el = document.createElement(file.type.startsWith("video") ? "video" : "audio");
      el.preload = "metadata";
      el.onloadedmetadata = () => resolve(el.duration);
      el.onerror = () => reject(new Error("Couldn't read that file's length."));
      el.src = url;
    });
  } finally {
    URL.revokeObjectURL(url);
  }
}

export async function signedUrl(key: string, seconds = 3600, download?: string): Promise<string | null> {
  const { data } = await supabaseBrowser().storage.from(BUCKET).createSignedUrl(key, seconds, download ? { download } : undefined);
  return data?.signedUrl ?? null;
}
