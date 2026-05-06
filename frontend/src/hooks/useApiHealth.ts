import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api-client";

export function useApiHealth() {
  return useQuery({
    queryKey: ["api-health"],
    queryFn: api.health,
    refetchInterval: 5000,
    retry: false
  });
}
