package vn.shoplens

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
