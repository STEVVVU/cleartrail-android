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

import com.google.samples.apps.nowinandroid.core.model.data.MAX_READING_BRIEF_ARTICLES
import com.google.samples.apps.nowinandroid.core.model.data.ReadingBriefArticle
import com.google.samples.apps.nowinandroid.core.model.data.ReadingBriefDraft
import com.google.samples.apps.nowinandroid.core.model.data.ReadingBriefSource
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.Serializable
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.security.MessageDigest

internal class ReadingBriefSession {
    private val mutex = Mutex()
    private var epoch = 0L
    private var nextToken = 0L
    private var grant: Grant? = null

    suspend fun invalidate() = mutex.withLock {
        epoch += 1
        grant = null
    }

    suspend fun authorize(preview: ReadingBriefPreview, destination: String): Long? = mutex.withLock {
        if (destination.isBlank() || !preview.isValid()) return@withLock null
        val authorizedAt = epoch
        nextToken += 1
        grant = Grant(preview.sha256, destination, authorizedAt, token = nextToken)
        nextToken
    }

    suspend fun revoke() = mutex.withLock {
        epoch += 1
        grant = null
    }

    suspend fun <T> write(
        token: Long,
        preview: ReadingBriefPreview,
        destination: String,
        writer: suspend (ByteArray) -> T,
    ): T? = mutex.withLock {
        val current = grant
        if (current == null || current.token != token || current.epoch != epoch ||
            current.digest != preview.sha256 || current.destination != destination || !preview.isValid()
        ) {
            return@withLock null
        }
        grant = null
        writer(preview.bytes.copyOf())
    }

    private data class Grant(
        val digest: String,
        val destination: String,
        val epoch: Long,
        val token: Long,
    )
}

internal fun previewReadingBrief(draft: ReadingBriefDraft): ReadingBriefPreview {
    require(draft.articles.isNotEmpty()) { "Add at least one saved article before reviewing." }
    require(draft.articles.size <= MAX_READING_BRIEF_ARTICLES)
    require(draft.privateNote.length <= 4_000)
    require(draft.articles.all { it.id.length <= 256 && it.title.length <= 1_000 && it.url.length <= 2_048 })
    val sources = buildSet {
        add(ReadingBriefSource.SAVED_SELECTION)
        if (draft.privateNote.isNotBlank()) add(ReadingBriefSource.PRIVATE_NOTE)
    }
    val payload = Json.encodeToString(
        BriefEnvelope(
            version = 1,
            sources = sources.map { it.name }.sorted(),
            articles = draft.articles.map { BriefArticle(it.id, it.title, it.url) },
            privateNote = draft.privateNote.takeIf(String::isNotBlank),
        ),
    )
    return ReadingBriefPreview.fromSerialized(payload.encodeToByteArray())
}

internal fun ReadingBriefDraft.replaceFromSaved(articles: List<ReadingBriefArticle>) =
    copy(articles = articles, privateNote = "")

@Serializable
internal data class BriefEnvelope(
    val version: Int,
    val sources: List<String>,
    val articles: List<BriefArticle>,
    val privateNote: String?,
)

@Serializable
internal data class BriefArticle(val id: String, val title: String, val url: String)

internal class ReadingBriefPreview private constructor(
    bytes: ByteArray,
    val sha256: String,
    sources: Set<ReadingBriefSource>,
) {
    private val frozenBytes = bytes.copyOf()
    val bytes: ByteArray get() = frozenBytes.copyOf()
    val sources: Set<ReadingBriefSource> = sources.toSet()

    fun isValid(): Boolean = runCatching {
        val decoded = fromSerialized(frozenBytes)
        decoded.sha256 == sha256 && decoded.sources == sources
    }.getOrDefault(false)

    companion object {
        fun fromSerialized(bytes: ByteArray): ReadingBriefPreview {
            val envelope = Json.decodeFromString<BriefEnvelope>(bytes.decodeToString())
            require(envelope.version == 1)
            require(envelope.articles.isNotEmpty() && envelope.articles.size <= MAX_READING_BRIEF_ARTICLES)
            require(envelope.privateNote == null || envelope.privateNote.length <= 4_000)
            require(envelope.articles.all { it.id.length <= 256 && it.title.length <= 1_000 && it.url.length <= 2_048 })
            val labels = envelope.sources.map { source ->
                ReadingBriefSource.entries.firstOrNull { it.name == source }
                    ?: throw IllegalArgumentException("Unsupported reading brief source label.")
            }
            require(labels.distinct().size == labels.size)
            val expected = buildSet {
                add(ReadingBriefSource.SAVED_SELECTION)
                if (!envelope.privateNote.isNullOrBlank()) add(ReadingBriefSource.PRIVATE_NOTE)
            }
            require(labels.toSet() == expected)
            require(envelope.sources == expected.map { it.name }.sorted())
            val digest = MessageDigest.getInstance("SHA-256").digest(bytes)
                .joinToString(separator = "") { byte -> "%02x".format(byte) }
            return ReadingBriefPreview(bytes, digest, expected)
        }
    }
}
