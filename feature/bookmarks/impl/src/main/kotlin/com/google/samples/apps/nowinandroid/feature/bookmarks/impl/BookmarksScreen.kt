/*
 * Copyright 2022 The Android Open Source Project
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

import android.content.ContentResolver
import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.annotation.VisibleForTesting
import androidx.compose.foundation.Image
import androidx.compose.foundation.gestures.Orientation
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.systemBars
import androidx.compose.foundation.layout.windowInsetsBottomHeight
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.layout.wrapContentSize
import androidx.compose.foundation.lazy.staggeredgrid.LazyVerticalStaggeredGrid
import androidx.compose.foundation.lazy.staggeredgrid.StaggeredGridCells
import androidx.compose.foundation.lazy.staggeredgrid.StaggeredGridItemSpan
import androidx.compose.foundation.lazy.staggeredgrid.rememberLazyStaggeredGridState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.tooling.preview.PreviewParameter
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.google.samples.apps.nowinandroid.core.designsystem.component.NiaButton
import com.google.samples.apps.nowinandroid.core.designsystem.component.NiaLoadingWheel
import com.google.samples.apps.nowinandroid.core.designsystem.component.NiaOutlinedButton
import com.google.samples.apps.nowinandroid.core.designsystem.component.NiaTextButton
import com.google.samples.apps.nowinandroid.core.designsystem.component.scrollbar.DraggableScrollbar
import com.google.samples.apps.nowinandroid.core.designsystem.component.scrollbar.rememberDraggableScroller
import com.google.samples.apps.nowinandroid.core.designsystem.component.scrollbar.scrollbarState
import com.google.samples.apps.nowinandroid.core.designsystem.theme.LocalTintTheme
import com.google.samples.apps.nowinandroid.core.designsystem.theme.NiaTheme
import com.google.samples.apps.nowinandroid.core.model.data.MAX_READING_BRIEF_ARTICLES
import com.google.samples.apps.nowinandroid.core.model.data.ReadingBriefArticle
import com.google.samples.apps.nowinandroid.core.model.data.UserNewsResource
import com.google.samples.apps.nowinandroid.core.ui.NewsFeedUiState
import com.google.samples.apps.nowinandroid.core.ui.NewsFeedUiState.Loading
import com.google.samples.apps.nowinandroid.core.ui.NewsFeedUiState.Success
import com.google.samples.apps.nowinandroid.core.ui.TrackScreenViewEvent
import com.google.samples.apps.nowinandroid.core.ui.TrackScrollJank
import com.google.samples.apps.nowinandroid.core.ui.UserNewsResourcePreviewParameterProvider
import com.google.samples.apps.nowinandroid.core.ui.newsFeed
import com.google.samples.apps.nowinandroid.feature.bookmarks.api.R

@Composable
internal fun BookmarksScreen(
    onTopicClick: (String) -> Unit,
    onShowSnackbar: suspend (String, String?) -> Boolean,
    modifier: Modifier = Modifier,
    viewModel: BookmarksViewModel = hiltViewModel(),
) {
    val feedState by viewModel.feedUiState.collectAsStateWithLifecycle()
    val briefViewModel: ReadingBriefViewModel = hiltViewModel()
    val briefState by briefViewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    var showBrief by remember { mutableStateOf(false) }
    val createDocument = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri ->
        briefViewModel.chooseDestination(uri, uri?.let { documentLabel(context.contentResolver, it) })
    }
    Box(modifier = modifier.fillMaxSize()) {
        BookmarksScreen(
            feedState = feedState,
            onShowSnackbar = onShowSnackbar,
            removeFromBookmarks = viewModel::removeFromSavedResources,
            onNewsResourceViewed = { viewModel.setNewsResourceViewed(it, true) },
            onTopicClick = onTopicClick,
            modifier = Modifier.fillMaxSize(),
            shouldDisplayUndoBookmark = viewModel.shouldDisplayUndoBookmark,
            undoBookmarkRemoval = viewModel::undoBookmarkRemoval,
            clearUndoState = viewModel::clearUndoState,
        )
        NiaButton(
            onClick = { showBrief = true },
            modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 24.dp),
        ) {
            Text(stringResource(R.string.feature_bookmarks_api_brief_action))
        }
    }
    if (showBrief) {
        ReadingBriefDialog(
            state = briefState,
            saved = (feedState as? Success)?.feed.orEmpty().map {
                ReadingBriefArticle(it.id, it.title, it.url)
            },
            onDismiss = { showBrief = false },
            onReplace = briefViewModel::replaceFromSaved,
            onNoteChange = briefViewModel::updateNote,
            onReview = briefViewModel::review,
            onChooseDestination = { createDocument.launch("reading-brief.json") },
            onApprove = briefViewModel::approve,
            onRevoke = briefViewModel::revoke,
            onWrite = { briefViewModel.write(context.contentResolver) },
        )
    }
}

private fun documentLabel(resolver: ContentResolver, uri: Uri): String {
    val name = runCatching {
        resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
            if (cursor.moveToFirst()) cursor.getString(0) else null
        }
    }.getOrNull()
    return listOfNotNull(name, uri.authority).joinToString(" · ").ifBlank { uri.lastPathSegment.orEmpty() }
}

@Composable
private fun ReadingBriefDialog(
    state: ReadingBriefUiState,
    saved: List<ReadingBriefArticle>,
    onDismiss: () -> Unit,
    onReplace: (List<ReadingBriefArticle>) -> Unit,
    onNoteChange: (String) -> Unit,
    onReview: () -> Unit,
    onChooseDestination: () -> Unit,
    onApprove: () -> Unit,
    onRevoke: () -> Unit,
    onWrite: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.feature_bookmarks_api_brief_title)) },
        text = {
            Column(
                modifier = Modifier.heightIn(max = 480.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(stringResource(R.string.feature_bookmarks_api_brief_intro))
                NiaOutlinedButton(onClick = { onReplace(saved.take(MAX_READING_BRIEF_ARTICLES)) }, enabled = !state.loading && saved.isNotEmpty()) {
                    Text(
                        if (saved.size > MAX_READING_BRIEF_ARTICLES) {
                            stringResource(R.string.feature_bookmarks_api_brief_replace_limited, MAX_READING_BRIEF_ARTICLES, saved.size)
                        } else {
                            stringResource(R.string.feature_bookmarks_api_brief_replace, saved.size)
                        },
                    )
                }
                OutlinedTextField(
                    value = state.draft.privateNote,
                    enabled = !state.loading,
                    onValueChange = onNoteChange,
                    label = { Text(stringResource(R.string.feature_bookmarks_api_brief_note)) },
                    supportingText = { Text(stringResource(R.string.feature_bookmarks_api_brief_note_help)) },
                    modifier = Modifier.fillMaxWidth(),
                )
                NiaOutlinedButton(onClick = onChooseDestination, enabled = !state.loading) {
                    Text(stringResource(R.string.feature_bookmarks_api_brief_choose))
                }
                state.destinationName?.let {
                    Text(stringResource(R.string.feature_bookmarks_api_brief_destination, it), maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                NiaOutlinedButton(onClick = onReview, enabled = !state.loading) {
                    Text(stringResource(R.string.feature_bookmarks_api_brief_review))
                }
                state.preview?.let { preview ->
                    Text(stringResource(R.string.feature_bookmarks_api_brief_sources, preview.sources.joinToString { it.name }))
                    Text(stringResource(R.string.feature_bookmarks_api_brief_hash, preview.sha256), style = MaterialTheme.typography.labelSmall)
                    Text(
                        text = preview.bytes.decodeToString(),
                        modifier = Modifier.fillMaxWidth(),
                        style = MaterialTheme.typography.bodySmall,
                    )
                    NiaButton(onClick = onApprove, enabled = state.destination != null) {
                        Text(stringResource(R.string.feature_bookmarks_api_brief_approve))
                    }
                    if (state.destination == null) {
                        Text(stringResource(R.string.feature_bookmarks_api_brief_no_destination))
                    }
                }
                if (state.grant != null) {
                    Text(stringResource(R.string.feature_bookmarks_api_brief_provider))
                    NiaButton(onClick = onWrite) { Text(stringResource(R.string.feature_bookmarks_api_brief_write)) }
                    NiaTextButton(onClick = onRevoke) { Text(stringResource(R.string.feature_bookmarks_api_brief_revoke)) }
                }
                state.status?.let { status ->
                    val isFailure = status in setOf(
                        R.string.feature_bookmarks_api_brief_failed,
                        R.string.feature_bookmarks_api_brief_invalid,
                        R.string.feature_bookmarks_api_brief_review_failed,
                        R.string.feature_bookmarks_api_brief_load_failed,
                        R.string.feature_bookmarks_api_brief_save_failed,
                    )
                    Text(
                        stringResource(status),
                        color = if (isFailure) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary,
                    )
                }
            }
        },
        confirmButton = {
            NiaTextButton(onClick = onDismiss) { Text(stringResource(R.string.feature_bookmarks_api_brief_close)) }
        },
    )
}

/**
 * Displays the user's bookmarked articles. Includes support for loading and empty states.
 */
@VisibleForTesting(otherwise = VisibleForTesting.PRIVATE)
@Composable
internal fun BookmarksScreen(
    feedState: NewsFeedUiState,
    onShowSnackbar: suspend (String, String?) -> Boolean,
    removeFromBookmarks: (String) -> Unit,
    onNewsResourceViewed: (String) -> Unit,
    onTopicClick: (String) -> Unit,
    modifier: Modifier = Modifier,
    shouldDisplayUndoBookmark: Boolean = false,
    undoBookmarkRemoval: () -> Unit = {},
    clearUndoState: () -> Unit = {},
) {
    val bookmarkRemovedMessage = stringResource(id = R.string.feature_bookmarks_api_removed)
    val undoText = stringResource(id = R.string.feature_bookmarks_api_undo)

    LaunchedEffect(shouldDisplayUndoBookmark) {
        if (shouldDisplayUndoBookmark) {
            val snackBarResult = onShowSnackbar(bookmarkRemovedMessage, undoText)
            if (snackBarResult) {
                undoBookmarkRemoval()
            } else {
                clearUndoState()
            }
        }
    }

    LifecycleEventEffect(Lifecycle.Event.ON_STOP) {
        clearUndoState()
    }

    when (feedState) {
        Loading -> LoadingState(modifier)
        is Success -> if (feedState.feed.isNotEmpty()) {
            BookmarksGrid(
                feedState,
                removeFromBookmarks,
                onNewsResourceViewed,
                onTopicClick,
                modifier,
            )
        } else {
            EmptyState(modifier)
        }
    }

    TrackScreenViewEvent(screenName = "Saved")
}

@Composable
private fun LoadingState(modifier: Modifier = Modifier) {
    NiaLoadingWheel(
        modifier = modifier
            .fillMaxWidth()
            .wrapContentSize()
            .testTag("bookmarks:loading"),
        contentDesc = stringResource(id = R.string.feature_bookmarks_api_loading),
    )
}

@Composable
private fun BookmarksGrid(
    feedState: NewsFeedUiState,
    removeFromBookmarks: (String) -> Unit,
    onNewsResourceViewed: (String) -> Unit,
    onTopicClick: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val scrollableState = rememberLazyStaggeredGridState()
    TrackScrollJank(scrollableState = scrollableState, stateName = "bookmarks:grid")
    Box(
        modifier = modifier
            .fillMaxSize(),
    ) {
        LazyVerticalStaggeredGrid(
            columns = StaggeredGridCells.Adaptive(300.dp),
            contentPadding = PaddingValues(16.dp),
            horizontalArrangement = Arrangement.spacedBy(16.dp),
            verticalItemSpacing = 24.dp,
            state = scrollableState,
            modifier = Modifier
                .fillMaxSize()
                .testTag("bookmarks:feed"),
        ) {
            newsFeed(
                feedState = feedState,
                onNewsResourcesCheckedChanged = { id, _ -> removeFromBookmarks(id) },
                onNewsResourceViewed = onNewsResourceViewed,
                onTopicClick = onTopicClick,
            )
            item(span = StaggeredGridItemSpan.FullLine) {
                Spacer(Modifier.windowInsetsBottomHeight(WindowInsets.safeDrawing))
            }
        }
        val itemsAvailable = when (feedState) {
            Loading -> 1
            is Success -> feedState.feed.size
        }
        val scrollbarState = scrollableState.scrollbarState(
            itemsAvailable = itemsAvailable,
        )
        scrollableState.DraggableScrollbar(
            modifier = Modifier
                .fillMaxHeight()
                .windowInsetsPadding(WindowInsets.systemBars)
                .padding(horizontal = 2.dp)
                .align(Alignment.CenterEnd),
            state = scrollbarState,
            orientation = Orientation.Vertical,
            onThumbMoved = scrollableState.rememberDraggableScroller(
                itemsAvailable = itemsAvailable,
            ),
        )
    }
}

@Composable
private fun EmptyState(modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .padding(16.dp)
            .fillMaxSize()
            .testTag("bookmarks:empty"),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        val iconTint = LocalTintTheme.current.iconTint
        Image(
            modifier = Modifier.fillMaxWidth(),
            painter = painterResource(id = R.drawable.feature_bookmarks_api_mg_empty_bookmarks),
            colorFilter = if (iconTint != Color.Unspecified) ColorFilter.tint(iconTint) else null,
            contentDescription = null,
        )

        Spacer(modifier = Modifier.height(48.dp))

        Text(
            text = stringResource(id = R.string.feature_bookmarks_api_empty_error),
            modifier = Modifier.fillMaxWidth(),
            textAlign = TextAlign.Center,
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold,
        )

        Spacer(modifier = Modifier.height(8.dp))

        Text(
            text = stringResource(id = R.string.feature_bookmarks_api_empty_description),
            modifier = Modifier.fillMaxWidth(),
            textAlign = TextAlign.Center,
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}

@Preview
@Composable
private fun LoadingStatePreview() {
    NiaTheme {
        LoadingState()
    }
}

@Preview
@Composable
private fun BookmarksGridPreview(
    @PreviewParameter(UserNewsResourcePreviewParameterProvider::class)
    userNewsResources: List<UserNewsResource>,
) {
    NiaTheme {
        BookmarksGrid(
            feedState = Success(userNewsResources),
            removeFromBookmarks = {},
            onNewsResourceViewed = {},
            onTopicClick = {},
        )
    }
}

@Preview
@Composable
private fun EmptyStatePreview() {
    NiaTheme {
        EmptyState()
    }
}
