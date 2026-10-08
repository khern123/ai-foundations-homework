import { useEffect, useState } from "react";
import { getProducts, type Product } from "./api.ts";

type State =
  | { kind: "loading" }
  | { kind: "ok"; products: Product[] }
  | { kind: "error"; message: string };

export function useProducts(): State {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    getProducts()
      .then((products) => setState({ kind: "ok", products }))
      .catch((err: Error) => setState({ kind: "error", message: err.message }));
  }, []);

  return state;
}
