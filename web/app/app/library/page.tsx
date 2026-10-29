import { PageHead } from "@/components/ui";
import { LibraryManager } from "./LibraryManager";
import { requireUser } from "@/lib/supabase/server";

export default async function LibraryPage() {
  const { supabase, user } = await requireUser();
  const [{ data: packs }, { data: assets }, { data: music }] = await Promise.all([
    supabase.from("footage_packs").select("id,name,owner_id,kind").order("name"),
    supabase.from("footage_assets").select("id,pack_id,kind"),
    supabase.from("music_tracks").select("id,name,mood,owner_id").order("name"),
  ]);
  const counts: Record<string, number> = {};
  (assets || []).forEach((a: { pack_id: string }) => (counts[a.pack_id] = (counts[a.pack_id] || 0) + 1));
  return (
    <>
      <PageHead title="Footage & music" sub="Footage packs are the visuals a video is cut from. Ready-made packs are shared; your own uploads are private to you." />
      <LibraryManager userId={user!.id} packs={(packs || []) as { id: string; name: string; owner_id: string | null }[]} counts={counts} music={(music || []) as { id: string; name: string; mood: string | null; owner_id: string | null }[]} />
    </>
  );
}
