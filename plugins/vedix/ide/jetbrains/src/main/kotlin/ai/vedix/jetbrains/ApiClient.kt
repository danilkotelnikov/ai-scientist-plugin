// ApiClient.kt — Dual-mode client over the Vedix.ai SaaS API.
//
// We use the standard library's java.net.http.HttpClient + gson; this avoids
// dragging OkHttp / Jackson into the plugin jar, keeping the .zip size small.
//
// Routing rule:
//   - If VEDIX_TOKEN is set (non-blank), every method talks to the SaaS at
//     VEDIX_SAAS_URL (default https://api.vedix.ai).
//   - Otherwise we delegate to CliRunner, which spawns the local `vedix` CLI.

package ai.vedix.jetbrains

import com.google.gson.Gson
import com.google.gson.annotations.SerializedName
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Duration

data class NewJobResult(
    @SerializedName("job_id") val jobId: String,
    val state: String? = null,
)

data class SwitchVenueResult(
    @SerializedName("job_id") val jobId: String? = null,
    val venue: String? = null,
)

object ApiClient {
    private val gson = Gson()
    private val http: HttpClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(15))
        .build()

    private val base: String
        get() = System.getenv("VEDIX_SAAS_URL") ?: "https://api.vedix.ai"

    private val token: String
        get() = System.getenv("VEDIX_TOKEN") ?: ""

    fun newJob(
        topic: String,
        discipline: String,
        language: String,
        venue: String,
    ): NewJobResult {
        if (token.isBlank()) {
            return CliRunner.newJob(topic, discipline, language, venue)
        }
        val payload = mapOf(
            "topic" to topic,
            "discipline" to discipline,
            "language" to language,
            "venue" to venue,
            "hypothesis_style" to "exploratory",
            "experiment_type" to "computational",
            "primary_metric" to "TBD",
            "expected_direction" to "increase",
            "tolerance" to 0.05,
        )
        val req = HttpRequest.newBuilder(URI.create("$base/v1/api/jobs"))
            .timeout(Duration.ofSeconds(30))
            .header("Authorization", "Bearer $token")
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(gson.toJson(payload)))
            .build()
        val resp = http.send(req, HttpResponse.BodyHandlers.ofString())
        if (resp.statusCode() !in 200..299) {
            throw RuntimeException("HTTP ${resp.statusCode()}: ${resp.body()}")
        }
        return gson.fromJson(resp.body(), NewJobResult::class.java)
    }

    fun switchVenue(jobId: String, venue: String): SwitchVenueResult {
        if (token.isBlank()) {
            return CliRunner.switchVenue(jobId, venue)
        }
        val payload = mapOf("venue" to venue)
        val req = HttpRequest.newBuilder(URI.create("$base/v1/api/jobs/$jobId/switch-venue"))
            .timeout(Duration.ofSeconds(30))
            .header("Authorization", "Bearer $token")
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(gson.toJson(payload)))
            .build()
        val resp = http.send(req, HttpResponse.BodyHandlers.ofString())
        if (resp.statusCode() !in 200..299) {
            throw RuntimeException("HTTP ${resp.statusCode()}: ${resp.body()}")
        }
        return gson.fromJson(resp.body(), SwitchVenueResult::class.java)
    }
}
