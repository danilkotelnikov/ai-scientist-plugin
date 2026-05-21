// CliRunner.kt — Plugin-only fallback. Drives the local `vedix` CLI on PATH.
//
// Used when VEDIX_TOKEN is not set: ApiClient.newJob / switchVenue delegate
// here and we shell out to `vedix <subcommand> ... --json`, parsing stdout
// as the corresponding result object.

package ai.vedix.jetbrains

import com.google.gson.Gson
import java.io.BufferedReader
import java.io.InputStreamReader

object CliRunner {
    private val gson = Gson()

    fun newJob(
        topic: String,
        discipline: String,
        language: String,
        venue: String,
    ): NewJobResult {
        val args = listOf(
            "vedix", "new",
            "--topic", topic,
            "--discipline", discipline,
            "--language", language,
            "--venue", venue,
            "--json",
        )
        val out = runCli(args)
        return gson.fromJson(out, NewJobResult::class.java)
    }

    fun switchVenue(jobId: String, venue: String): SwitchVenueResult {
        val args = listOf(
            "vedix", "switch", "venue",
            "--job", jobId,
            "--venue", venue,
            "--json",
        )
        val out = runCli(args)
        return gson.fromJson(out, SwitchVenueResult::class.java)
    }

    private fun runCli(args: List<String>): String {
        val pb = ProcessBuilder(args).redirectErrorStream(false)
        val proc = pb.start()
        val out = BufferedReader(InputStreamReader(proc.inputStream)).use { it.readText() }
        val err = BufferedReader(InputStreamReader(proc.errorStream)).use { it.readText() }
        val code = proc.waitFor()
        if (code != 0) {
            throw RuntimeException("vedix CLI exited $code: ${err.trim()}")
        }
        return out
    }
}
