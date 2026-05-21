// NewManuscriptAction.kt — "Vedix: New Manuscript" action.
//
// Collects topic, discipline, language, and venue through three modal dialogs
// (showInputDialog / showEditableChooseDialog) and dispatches to ApiClient.
// Errors are surfaced via Messages.showErrorDialog rather than thrown, so the
// user never sees a "Plugin Error" notification balloon.

package ai.vedix.jetbrains

import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.ui.Messages

class NewManuscriptAction : AnAction() {

    override fun actionPerformed(e: AnActionEvent) {
        val topic = Messages.showInputDialog(
            e.project,
            "Research topic:",
            "Vedix — New Manuscript",
            null,
        ) ?: return

        val discipline = Messages.showEditableChooseDialog(
            "Discipline:",
            "Vedix — New Manuscript",
            null,
            DISCIPLINES,
            "chemistry",
            null,
        ) ?: return

        val language = Messages.showEditableChooseDialog(
            "Manuscript language:",
            "Vedix — New Manuscript",
            null,
            LANGUAGES,
            "en",
            null,
        ) ?: return

        val venue = Messages.showInputDialog(
            e.project,
            "Target venue (e.g. preprint, elsevier:cell-reports-medicine):",
            "Vedix — New Manuscript",
            null,
            "preprint",
            null,
        ) ?: return

        try {
            val r = ApiClient.newJob(
                topic = topic,
                discipline = discipline,
                language = language,
                venue = venue,
            )
            Messages.showInfoMessage(
                e.project,
                "Job ${r.jobId} queued (state: ${r.state ?: "pending"})",
                "Vedix",
            )
        } catch (ex: Exception) {
            Messages.showErrorDialog(
                e.project,
                "Failed to start Vedix job: ${ex.message}",
                "Vedix",
            )
        }
    }

    companion object {
        private val DISCIPLINES = arrayOf(
            "chemistry",
            "biology",
            "medicine",
            "physics",
            "mathematics",
            "geology",
            "computer_science",
            "humanities",
        )
        private val LANGUAGES = arrayOf("en", "ru", "es", "de", "fr", "zh", "ja")
    }
}
