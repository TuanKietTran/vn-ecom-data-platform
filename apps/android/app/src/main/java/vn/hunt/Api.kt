package vn.hunt

import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

val wireJson = Json {
    ignoreUnknownKeys = true
    encodeDefaults = true
}

class Api(private val base: String) {
    suspend fun request(path: String, body: String? = null): String =
        withContext(Dispatchers.IO) {
            val root = URI(base)
            require(
                root.scheme in listOf("https", "http") && root.host != null && root.userInfo == null
            ) {
                "Set a valid gateway URL in Connection settings."
            }
            val connection =
                URL(base.trimEnd('/') + "/" + path).openConnection() as HttpURLConnection
            try {
                connection.connectTimeout = 10000
                connection.readTimeout = 65000
                if (body != null) {
                    connection.requestMethod = "POST"
                    connection.doOutput = true
                    connection.setRequestProperty("Content-Type", "application/json")
                    connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
                }
                val status = connection.responseCode
                val text =
                    (if (status in 200..299) connection.inputStream else connection.errorStream)
                        ?.bufferedReader()
                        ?.use { it.readText() }
                        .orEmpty()
                if (status !in 200..299) {
                    val error =
                        runCatching {
                                wireJson
                                    .parseToJsonElement(text)
                                    .jsonObject["message"]
                                    ?.jsonPrimitive
                                    ?.content
                            }
                            .getOrNull()
                    throw IllegalStateException(
                        error ?: "The platform could not complete this request."
                    )
                }
                text
            } finally {
                connection.disconnect()
            }
        }
}
