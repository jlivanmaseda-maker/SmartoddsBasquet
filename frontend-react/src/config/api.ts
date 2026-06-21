/** Minimal GraphQL fetch helper (same origin, no auth) for SmartOdds Basket. */

export async function gql<T = unknown>(
  query: string,
  variables: Record<string, unknown> = {},
): Promise<T> {
  const res = await fetch("/graphql", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, variables }),
  });
  const json = await res.json();
  if (json.errors) {
    throw new Error(json.errors.map((e: { message: string }) => e.message).join("; "));
  }
  return json.data as T;
}
