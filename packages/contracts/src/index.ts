import { z } from "zod";
const money = z.number().int().nonnegative().max(Number.MAX_SAFE_INTEGER);
export const dealRequest = z
  .object({
    query: z.string().trim().min(2).max(300),
    product_key: z.string().nullable().optional(),
    target_vnd: money.nullable().optional(),
    include_synthetic: z.boolean().default(false),
    eligibility: z
      .object({
        payment_method: z.string().max(200).nullable().optional(),
        memberships: z.array(z.string().max(200)).max(20).nullable().optional(),
        new_user: z.boolean().nullable().optional(),
      })
      .default({}),
  })
  .strict();
export const chatRequest = z
  .object({
    message: z.string().trim().min(1).max(8000),
    history: z
      .array(
        z.object({
          role: z.enum(["user", "assistant"]),
          content: z.string().min(1).max(8000),
        }),
      )
      .max(20)
      .default([]),
  })
  .strict();
export type DealRequest = z.infer<typeof dealRequest>;
export interface Offer {
  offer_id: string;
  product_key: string;
  title: string;
  platform: string;
  seller: string;
  price_vnd: number;
  shipping_vnd: number | null;
  observed_at: string;
  source: string;
  source_tier: string;
  url: string | null;
  in_stock: boolean | null;
  variant_verified: boolean;
}
export interface Deal {
  offer: Offer;
  checkout_vnd: number | null;
  item_after_discount_vnd: number;
  shipping_after_discount_vnd: number | null;
  discounts: { code: string; scope: string; discount_vnd: number }[];
  cashback_vnd: number;
  conditions: string[];
  voucher_codes: string[];
  eligible: boolean;
  within_target: boolean | null;
  checked_at: string;
  lowest_observed_item_price_vnd: number | null;
  price_history_days: number;
}
export interface DealResults {
  eligible: Deal[];
  conditional: Deal[];
  fewest_conditions: Deal[];
  price_history?: Deal[];
  catalog_offer_count: number;
  notice: string;
}
export interface Product {
  index_id: string;
  title: string;
  platform: string;
  source: string;
  source_tier: string;
  price_vnd: number;
  captured_at: string;
  url?: string;
  product_id: string;
  sku_id?: string;
}
export interface ChatStatus {
  data_available: boolean;
  model_configured: boolean;
  model: string;
  sources: string[];
}
export interface Turn {
  role: "user" | "assistant";
  content: string;
}
export interface ChatReply {
  answer: string;
  model: string;
  context_source: string | null;
  intent?: string;
  action?: string;
  products?: Product[];
}
