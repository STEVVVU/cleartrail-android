/*
 * Copyright 2026 The Android Open Source Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package com.google.samples.apps.nowinandroid.feature.bookmarks.impl

import com.google.samples.apps.nowinandroid.core.model.data.ReadingBriefArticle
import com.google.samples.apps.nowinandroid.core.model.data.ReadingBriefDraft
import com.google.samples.apps.nowinandroid.core.model.data.ReadingBriefSource
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.async
import kotlinx.coroutines.test.runTest
import org.junit.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ReadingBriefSessionTest {
    private val draft = ReadingBriefDraft(
        articles = listOf(ReadingBriefArticle("a1", "Systems", "https://example.test/a1")),
        privateNote = "Read later",
    )

    @Test
    fun previewCarriesSelectionAndNoteLabelsAndExactBytesAreFrozen() {
        val preview = previewReadingBrief(draft)
        val original = preview.bytes
        assertEquals(setOf(ReadingBriefSource.SAVED_SELECTION, ReadingBriefSource.PRIVATE_NOTE), preview.sources)
        assertTrue(original.decodeToString().contains("PRIVATE_NOTE"))
        original[0] = 0
        assertTrue(preview.bytes.decodeToString().startsWith("{"))
    }

    @Test
    fun serializedPayloadCannotDropOrInventThePrivateNoteLabel() {
        val missing = """{"version":1,"sources":["SAVED_SELECTION"],"articles":[{"id":"a1","title":"Systems","url":"https://example.test/a1"}],"privateNote":"Read later"}"""
        val invented = """{"version":1,"sources":["SAVED_SELECTION","PRIVATE_NOTE"],"articles":[{"id":"a1","title":"Systems","url":"https://example.test/a1"}],"privateNote":null}"""

        assertFailsWith<IllegalArgumentException> {
            ReadingBriefPreview.fromSerialized(missing.encodeToByteArray())
        }
        assertFailsWith<IllegalArgumentException> {
            ReadingBriefPreview.fromSerialized(invented.encodeToByteArray())
        }
    }

    @Test
    fun editingContentChangesDigestAndInvalidatesGrant() = runTest {
        val session = ReadingBriefSession()
        val before = previewReadingBrief(draft)
        val token = assertNotNull(session.authorize(before, "content://provider/brief"))
        val edited = previewReadingBrief(draft.copy(privateNote = "Changed"))
        assertTrue(before.sha256 != edited.sha256)
        assertNull(session.write(token, edited, "content://provider/brief") { it.size })
    }

    @Test
    fun destinationAndRevocationAreBoundToOneUseApproval() = runTest {
        val session = ReadingBriefSession()
        val preview = previewReadingBrief(draft)
        val token = assertNotNull(session.authorize(preview, "content://provider/one"))
        assertNull(session.write(token, preview, "content://provider/two") { it.size })
        session.revoke()
        assertNull(session.write(token, preview, "content://provider/one") { it.size })

        val second = assertNotNull(session.authorize(preview, "content://provider/one"))
        assertEquals(preview.bytes.size, session.write(second, preview, "content://provider/one") { it.size })
        assertNull(session.write(second, preview, "content://provider/one") { it.size })
    }

    @Test
    fun sinkReceivesOnlyTheExactApprovedPayload() = runTest {
        val session = ReadingBriefSession()
        val preview = previewReadingBrief(draft)
        var written: ByteArray? = null
        assertNull(session.write(1, preview, "content://provider/one") { bytes -> written = bytes })
        assertNull(written)

        val token = assertNotNull(session.authorize(preview, "content://provider/one"))
        assertNotNull(session.write(token, preview, "content://provider/one") { bytes -> written = bytes })
        assertTrue(preview.bytes.contentEquals(assertNotNull(written)))
    }

    @Test
    fun failedWriteConsumesApprovalAndRequiresNewReview() = runTest {
        val session = ReadingBriefSession()
        val preview = previewReadingBrief(draft)
        val token = assertNotNull(session.authorize(preview, "content://provider/one"))
        runCatching {
            session.write(token, preview, "content://provider/one") { error("provider stopped after partial bytes") }
        }
        assertNull(session.write(token, preview, "content://provider/one") { it.size })
        val fresh = assertNotNull(session.authorize(preview, "content://provider/one"))
        assertNotNull(session.write(fresh, preview, "content://provider/one") { it.size })
    }

    @Test
    fun revocationWaitsForAnActiveWriteAndBlocksTheNextWrite() = runTest {
        val session = ReadingBriefSession()
        val preview = previewReadingBrief(draft)
        val token = assertNotNull(session.authorize(preview, "content://provider/one"))
        val writerStarted = CompletableDeferred<Unit>()
        val finishWriter = CompletableDeferred<Unit>()
        val write = async {
            session.write(token, preview, "content://provider/one") {
                writerStarted.complete(Unit)
                finishWriter.await()
                it.size
            }
        }
        writerStarted.await()
        val revoke = async { session.revoke() }
        assertTrue(!revoke.isCompleted)
        finishWriter.complete(Unit)
        assertNotNull(write.await())
        revoke.await()
        assertNull(session.write(token, preview, "content://provider/one") { it.size })
    }

    @Test
    fun replacingSavedItemsIsExplicitAndClearsPrivateNote() {
        val replaced = draft.replaceFromSaved(listOf(ReadingBriefArticle("b2", "Networks", "https://example.test/b2")))
        assertEquals(listOf("b2"), replaced.articles.map { it.id })
        assertEquals("", replaced.privateNote)
    }
}
