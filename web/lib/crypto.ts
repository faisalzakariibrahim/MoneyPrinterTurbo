import "server-only";
import { createCipheriv, createDecipheriv, randomBytes } from "crypto";

// AES-256-GCM, wire format base64(iv12 | ciphertext | tag16) — matches app/longform/secrets_box.py
function key(): Buffer {
  const k = Buffer.from(process.env.LF_TOKEN_ENC_KEY || "", "base64");
  if (k.length !== 32) throw new Error("LF_TOKEN_ENC_KEY must be 32 bytes base64");
  return k;
}

export function encrypt(plain: string): string {
  const iv = randomBytes(12);
  const c = createCipheriv("aes-256-gcm", key(), iv);
  const ct = Buffer.concat([c.update(plain, "utf8"), c.final()]);
  return Buffer.concat([iv, ct, c.getAuthTag()]).toString("base64");
}

export function decrypt(token: string): string {
  const blob = Buffer.from(token, "base64");
  const d = createDecipheriv("aes-256-gcm", key(), blob.subarray(0, 12));
  d.setAuthTag(blob.subarray(blob.length - 16));
  return Buffer.concat([d.update(blob.subarray(12, blob.length - 16)), d.final()]).toString("utf8");
}
