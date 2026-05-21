// SwitchVenueAction.kt — "Vedix: Switch Venue" action.
//
// Prompts for a job id and a new venue and pipes them through ApiClient,
// which routes via the SaaS HTTP API when VEDIX_TOKEN is set, or via the
// local `vedix` CLI otherwise.

package ai.vedix.jetbrains

import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.ui.Messages

class SwitchVenueAction : AnAction() {

    override fun actionPerformed(e: AnActionEvent) {
        val jobId = Messages.showInputDialog(
            e.project,
            "Job ID:",
            "Vedix — Switch Venue",
            null,
        ) ?: return

        val venue = Messages.showInputDialog(
            e.project,
            "Switch to venue (e.g. elsevier:cell-reports-medicine):",
            "Vedix — Switch Venue",
            null,
        ) ?: return

        try {
            ApiClient.switchVenue(jobId = jobId, venue = venue)
            Messages.showInfoMessage(
                e.project,
                "Venue switched to $venue for job $jobId",
                "Vedix",
            )
        } catch (ex: Exception) {
            Messages.showErrorDialog(
                e.project,
                "Failed to switch venue: ${ex.message}",
                "Vedix",
            )
        }
    }
}
