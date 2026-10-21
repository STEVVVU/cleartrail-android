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

package com.google.samples.apps.nowinandroid.core.data.repository

import com.google.samples.apps.nowinandroid.core.database.dao.ReadingBriefDraftDao
import com.google.samples.apps.nowinandroid.core.database.model.ReadingBriefDraftEntity
import com.google.samples.apps.nowinandroid.core.model.data.ReadingBriefArticle
import com.google.samples.apps.nowinandroid.core.model.data.ReadingBriefDraft
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import org.junit.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class ReadingBriefDraftRepositoryTest {
    @Test
    fun savingAndReloadingDraftPreservesKnownSourceLabelsAndContent() = runTest {
        val dao = FakeReadingBriefDraftDao()
        val repository = OfflineFirstReadingBriefDraftRepository(dao)
        val draft = ReadingBriefDraft(
            articles = listOf(ReadingBriefArticle("a1", "Systems", "https://example.test/a1")),
            privateNote = "My note",
        )

        repository.saveDraft(draft)

        assertEquals(draft, repository.observeDraft().first())
        val stored = dao.entity.value!!.payload
        assertEquals(true, stored.contains("SAVED_SELECTION"))
        assertEquals(true, stored.contains("PRIVATE_NOTE"))
    }

    @Test
    fun unknownStoredSourceLabelFailsClosed() = runTest {
        val dao = FakeReadingBriefDraftDao()
        dao.entity.value = ReadingBriefDraftEntity(
            payload = """{"articles":[],"privateNote":"","sources":["SAVED_SELECTION","FUTURE_PRIVATE_SOURCE"]}""",
        )

        assertFailsWith<IllegalArgumentException> {
            OfflineFirstReadingBriefDraftRepository(dao).observeDraft().first()
        }
    }

    private class FakeReadingBriefDraftDao : ReadingBriefDraftDao {
        val entity = MutableStateFlow<ReadingBriefDraftEntity?>(null)

        override fun observeDraft(): Flow<ReadingBriefDraftEntity?> = entity

        override suspend fun saveDraft(draft: ReadingBriefDraftEntity) {
            entity.value = draft
        }
    }
}
