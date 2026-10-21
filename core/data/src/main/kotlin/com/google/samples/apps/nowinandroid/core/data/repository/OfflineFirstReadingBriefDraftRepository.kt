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
import com.google.samples.apps.nowinandroid.core.model.data.MAX_READING_BRIEF_ARTICLES
import com.google.samples.apps.nowinandroid.core.model.data.ReadingBriefArticle
import com.google.samples.apps.nowinandroid.core.model.data.ReadingBriefDraft
import com.google.samples.apps.nowinandroid.core.model.data.ReadingBriefSource
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import javax.inject.Inject

internal class OfflineFirstReadingBriefDraftRepository @Inject constructor(
    private val dao: ReadingBriefDraftDao,
) : ReadingBriefDraftRepository {
    private val json = Json

    override fun observeDraft(): Flow<ReadingBriefDraft?> = dao.observeDraft().map { entity ->
        entity?.let {
            val stored = json.decodeFromString<StoredBriefDraft>(it.payload)
            val sources = stored.sources.map { source ->
                ReadingBriefSource.entries.firstOrNull { it.name == source }
                    ?: throw IllegalArgumentException("Unsupported reading brief source label.")
            }.toSet()
            require(sources.contains(ReadingBriefSource.SAVED_SELECTION))
            val expected = buildSet {
                add(ReadingBriefSource.SAVED_SELECTION)
                if (stored.privateNote.isNotBlank()) add(ReadingBriefSource.PRIVATE_NOTE)
            }
            require(stored.sources.distinct().size == stored.sources.size)
            require(sources == expected)
            require(stored.articles.size <= MAX_READING_BRIEF_ARTICLES)
            require(stored.privateNote.length <= MAX_NOTE_LENGTH)
            require(stored.articles.all { it.id.length <= 256 && it.title.length <= 1_000 && it.url.length <= 2_048 })
            ReadingBriefDraft(
                articles = stored.articles.map { article ->
                    ReadingBriefArticle(article.id, article.title, article.url)
                },
                privateNote = stored.privateNote,
            )
        }
    }

    override suspend fun saveDraft(draft: ReadingBriefDraft) {
        require(draft.articles.size <= MAX_READING_BRIEF_ARTICLES)
        require(draft.privateNote.length <= MAX_NOTE_LENGTH)
        require(draft.articles.all { it.id.length <= 256 && it.title.length <= 1_000 && it.url.length <= 2_048 })
        val stored = StoredBriefDraft(
            articles = draft.articles.map { StoredArticle(it.id, it.title, it.url) },
            privateNote = draft.privateNote,
            sources = buildList {
                add(ReadingBriefSource.SAVED_SELECTION.name)
                if (draft.privateNote.isNotBlank()) add(ReadingBriefSource.PRIVATE_NOTE.name)
            },
        )
        dao.saveDraft(ReadingBriefDraftEntity(payload = json.encodeToString(stored)))
    }

    private companion object {
        const val MAX_NOTE_LENGTH = 4_000
    }
}

@Serializable
private data class StoredBriefDraft(
    val articles: List<StoredArticle>,
    val privateNote: String,
    val sources: List<String>,
)

@Serializable
private data class StoredArticle(val id: String, val title: String, val url: String)
