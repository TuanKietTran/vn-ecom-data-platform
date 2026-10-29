package vn.hunt

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class Offer(
    @SerialName("offer_id") val id: String,
    @SerialName("product_key") val productKey: String,
    val title: String,
    val platform: String,
    val seller: String,
    @SerialName("price_vnd") val price: Long,
    @SerialName("observed_at") val observed: String,
    val source: String,
    @SerialName("source_tier") val sourceTier: String,
    val url: String? = null,
)

@Serializable
data class Discount(
    val code: String,
    val scope: String,
    @SerialName("discount_vnd") val amount: Long,
)

@Serializable
data class Deal(
    val offer: Offer,
    @SerialName("checkout_vnd") val checkout: Long? = null,
    @SerialName("shipping_after_discount_vnd") val shipping: Long? = null,
    val discounts: List<Discount> = emptyList(),
    @SerialName("cashback_vnd") val cashback: Long = 0,
    val conditions: List<String> = emptyList(),
    @SerialName("voucher_codes") val codes: List<String> = emptyList(),
    val eligible: Boolean = false,
    @SerialName("within_target") val withinTarget: Boolean? = null,
    @SerialName("checked_at") val checked: String,
    @SerialName("lowest_observed_item_price_vnd") val historyLow: Long? = null,
    @SerialName("price_history_days") val historyDays: Int = 0,
)

@Serializable
data class DealResults(
    val eligible: List<Deal> = emptyList(),
    val conditional: List<Deal> = emptyList(),
    @SerialName("fewest_conditions") val fewest: List<Deal> = emptyList(),
    val notice: String = "",
)

@Serializable
data class Product(
    @SerialName("index_id") val id: String,
    val title: String,
    val platform: String,
    @SerialName("source_tier") val sourceTier: String,
    @SerialName("price_vnd") val price: Long,
    @SerialName("captured_at") val captured: String,
    val url: String? = null,
)

@Serializable
 data class UpcomingDeal(
    val code: String,
    val platform: String,
    val seller: String? = null,
    @SerialName("product_keys") val productKeys: List<String> = emptyList(),
    @SerialName("starts_at") val startsAt: String,
    @SerialName("expires_at") val expiresAt: String,
    @SerialName("discount_vnd") val discount: Long,
    val percent: Int,
    @SerialName("cap_vnd") val cap: Long? = null,
    @SerialName("min_spend_vnd") val minimumSpend: Long,
    val eligibility: List<String> = emptyList(),
    @SerialName("checkout_payment_method") val checkoutPaymentMethod: String? = null,
    @SerialName("cashback_vnd") val cashback: Long,
    @SerialName("evidence_source") val evidenceSource: String,
    @SerialName("evidence_url") val evidenceUrl: String? = null,
    @SerialName("as_of") val asOf: String,
    val synthetic: Boolean,
) { val id: String get() = "$platform:$code" }

@Serializable
 data class UpcomingResults(
    val deals: List<UpcomingDeal> = emptyList(),
    @SerialName("synthetic_included") val syntheticIncluded: Boolean = false,
    val notice: String = "",
)

@Serializable data class Products(val products: List<Product>)

@Serializable
data class Status(
    @SerialName("data_available") val dataAvailable: Boolean,
    @SerialName("model_configured") val modelConfigured: Boolean,
    val model: String,
)

@Serializable
data class Eligibility(
    @SerialName("payment_method") val payment: String? = null,
    val memberships: List<String>? = null,
    @SerialName("new_user") val newUser: Boolean? = null,
)

@Serializable
data class HuntRequest(
    val query: String,
    @SerialName("target_vnd") val target: Long? = null,
    @SerialName("product_key") val variant: String? = null,
    @SerialName("include_synthetic") val demo: Boolean = false,
    val eligibility: Eligibility = Eligibility(),
)

@Serializable data class Turn(val role: String, val content: String)

@Serializable data class ChatRequest(val message: String, val history: List<Turn>)

@Serializable data class Reply(val answer: String, val action: String? = null)
