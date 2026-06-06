import { redirect } from "next/navigation";

/** Back-compat: editor lives at `/`. */
export default function StudioRedirectPage() {
  redirect("/");
}
