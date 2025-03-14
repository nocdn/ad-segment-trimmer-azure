<script>
  let file = $state(null);
  let isDragging = $state(false);
  let uploading = $state(false);
  let downloadUrl = $state("");
  let errorMsg = $state("");

  // When a file is dragged over the dropzone, prevent default behavior
  function dragOver(event) {
    event.preventDefault();
    isDragging = true;
    console.log("dragging");
  }

  // When the dragged file leaves the dropzone
  function dragLeave(event) {
    event.preventDefault();
    isDragging = false;
  }

  // When a file is dropped in the dropzone
  function drop(event) {
    event.preventDefault();
    isDragging = false;
    if (event.dataTransfer.files.length) {
      file = event.dataTransfer.files[0];
    }
  }

  // Handles changes from the hidden file input (click-to-select)
  function handleFileChange(event) {
    const files = event.target.files;
    if (files && files.length > 0) {
      file = files[0];
    }
  }

  // Submit the file to the Flask API endpoint
  async function submitFile() {
    if (!file) return;
    uploading = true;
    errorMsg = "";
    downloadUrl = "";

    const formData = new FormData();
    formData.append("file", file);

    try {
      // Change the URL below to your API's address if needed
      const response = await fetch("/process", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        errorMsg = `Error: ${response.status} ${response.statusText}`;
      } else {
        const blob = await response.blob();
        // Create an object URL for the blob to trigger download later
        downloadUrl = URL.createObjectURL(blob);
      }
    } catch (err) {
      errorMsg = "Error: " + err;
    } finally {
      uploading = false;
    }
  }
</script>

<main class="flex flex-col gap-4 items-center justify-center min-h-screen">
  <button
    class="w-64 h-36 rounded-2xl border-dotted font-mono p-4 grid place-content-center text-center {isDragging
      ? 'border-blue-500 border-3'
      : 'border-gray-300 border-2'}"
    aria-label="Dropzone for audio file"
    tabindex="0"
    ondragover={dragOver}
    ondragleave={dragLeave}
    ondrop={drop}
    onclick={() => document.getElementById("file-input").click()}
  >
    {#if file}
      <p>{file.name}</p>
    {:else}
      <p>Drop an audio file here, or click to select one.</p>
    {/if}
    <input
      id="file-input"
      type="file"
      accept="audio/*"
      onchange={handleFileChange}
      style="display: none;"
    />
  </button>

  <!-- Submit button or Download button -->
  <div class="rounded-xl border border-gray-200 px-4 py-3 w-fit font-medium">
    {#if downloadUrl}
      <!-- When processed, show a download button -->
      <a
        download={file
          ? file.name.replace(/\.[^/.]+$/, "_edited.mp3")
          : "edited.mp3"}
        href={downloadUrl}
      >
        <button>Download Edited File</button>
      </a>
    {:else}
      <!-- Otherwise, a submit button -->
      <button onclick={submitFile} disabled={!file || uploading}>
        {uploading ? "Processing..." : "Submit"}
      </button>
    {/if}
  </div>

  {#if errorMsg}
    <p style="color:red;">{errorMsg}</p>
  {/if}
</main>
