# Cleartrail

Cleartrail is an Android reading app with a local, consent-gated reading brief. It builds on the full [Now in Android](https://github.com/android/nowinandroid) application and retains its Apache-2.0 license, upstream history, and notices. The original project README is preserved in [`README.upstream.md`](README.upstream.md).

## Reading brief

From **Saved**, explicitly replace the local draft with saved articles, optionally add a private note, review the exact JSON and its SHA-256 digest, choose a document destination, and approve one write. The serialized source labels retain `SAVED_SELECTION` for the selected reading list and add `PRIVATE_NOTE` when a note is present. Unknown stored labels stop loading instead of losing their meaning. A brief holds up to 500 articles; for larger Saved lists, the replacement button explicitly offers the first 500 in the current list order.

Room stores draft content in schema 15. It does not store approval. A draft edit, a destination change, or revocation clears the one-use in-memory approval. The document provider may create an empty file before approval. The app writes no payload until the reviewed bytes and selected destination have a current approval. A provider can fail after accepting some bytes; the app consumes approval before opening the stream and requires a new review after failure.

This is a bounded, cooperative data-flow example inspired by explicit labels in [TaintDroid](https://www.usenix.org/events/osdi10/tech/full_papers/Enck.pdf), sections 4.1 and 4.2. It does not instrument Android, track implicit flows or third-party code, retract exported copies, or provide an atomic filesystem transaction. The workflow adapts the explicit privacy mediator in Carnegie Mellon's [December 2016 project archive](https://www.andrew.cmu.edu/course/15-821/archive/), which focuses on audio data. Cleartrail applies the idea to saved reading metadata and does not implement the audio assignment.

## Build and test

Use JDK 21 and the checked-in Gradle wrapper.

```sh
./gradlew :app:assembleDemoDebug :app:assembleDemoDebugAndroidTest :core:database:assembleDemoDebugAndroidTest
./gradlew :core:data:testDemoDebugUnitTest :feature:bookmarks:impl:testDemoDebugUnitTest :feature:bookmarks:impl:lintDemoDebug
```

Run `python -m unittest discover -s tools -p test_verify_cleartrail.py` for the verifier's platform and artifact-boundary tests. The native emulator workflow is an optional manual dispatch. A successful build or an unrun emulator job does not prove document-provider behavior or native screen acceptance.

Current local checks pass the 11 Python verifier tests. Android compilation, Kotlin tests and lint await the hosted run. The Room upgrade/reopen test sources are included in the database instrumentation APK build, but their execution and the real document-provider flow remain unverified.

## Architecture

`core:model` defines the persisted draft and source categories. `core:data` validates and serializes the draft through the existing repository boundary. `core:database` stores draft-only content with an additive Room migration. The Saved feature owns the Compose review flow and the transient approval session. Android's Storage Access Framework supplies the user-selected document destination.

## Upstream attribution

Cleartrail retains the complete upstream Now in Android history at the pinned base revision `a49ed253d75e61a2b6ab80a8da677b57437b08eb`. Existing upstream files keep their original notices. New Cleartrail files carry their own Apache-2.0 notices. See [`LICENSE`](LICENSE), [`NOTICE`](NOTICE), and [`README.upstream.md`](README.upstream.md).
