// static/js/scanner.js

/**
 * Handles the successful scan of a QR code.
 * @param {string} decodedText - The decoded text from the QR code (expected to be the unique_id).
 * @param {object} decodedResult - Detailed information about the scan result.
 */
function onScanSuccess(decodedText, decodedResult) {
    console.log(`Raw QR Code Text: ${decodedText}`);
    displayScanError(''); // Clear previous errors

    // Assume decodedText is the unique_id
    const extinguisherId = decodedText.trim();

    // Basic validation (optional, but recommended)
    // Check if it looks somewhat like a UUID or has a reasonable length
    if (extinguisherId && extinguisherId.length > 10) { // Adjust length check if needed

        const checkUrl = window.location.origin + '/check/' + extinguisherId;
        console.log(`Constructed Check-in URL: ${checkUrl}`);

        // --- STOP THE SCANNER ---
        // Access the scanner instance from the window object
        if (window.html5QrcodeScanner && typeof window.html5QrcodeScanner.clear === 'function') {
            console.log("Stopping the scanner...");
            // Optionally update UI to show "Processing..."
            const resultsDiv = document.getElementById('qr-reader-results');
            if(resultsDiv) resultsDiv.innerHTML = 'QR Code Scanned. Processing...';

            window.html5QrcodeScanner.clear() // Call the clear method
                .then(() => {
                    console.log("Scanner stopped successfully.");
                    // Redirect *after* successful stop
                    console.log(`Redirecting to: ${checkUrl}`);
                    window.location.href = checkUrl;
                })
                .catch((error) => {
                    console.error("Failed to clear/stop scanner:", error);
                    // Fallback: Redirect even if stopping failed, as scan was successful
                    console.warn("Scanner stop failed, but redirecting anyway.");
                    window.location.href = checkUrl;
                });
        } else {
            console.warn("Scanner object (window.html5QrcodeScanner) or clear method not found. Cannot stop automatically.");
            // Fallback: Redirect immediately if scanner object isn't available
            console.log(`Redirecting (scanner stop unavailable): ${checkUrl}`);
            window.location.href = checkUrl;
        }
        // --- END STOP THE SCANNER ---

    } else {
        console.error("Scanned data doesn't look like a valid ID:", decodedText);
        displayScanError('Invalid QR Code scanned.');
        // Do NOT redirect if the ID looks invalid
    }
}

/**
 * Handles errors during the scanning process (e.g., no QR code found in frame).
 * @param {string} error - The error message.
 */
function onScanFailure(error) {
    // Ignore frequent 'no code found' errors unless needed for debugging
    // console.warn(`QR Code scan error: ${error}`);
}

// Helper to display errors on the scan page
function displayScanError(message) {
    const errorElement = document.getElementById('scanErrorDisplay'); // Make sure this element exists in scan.html
    if (errorElement) {
        errorElement.textContent = message;
        errorElement.style.color = 'red'; // Ensure errors are visible
    }
}

// --- Initialize the Scanner when the DOM is ready ---
document.addEventListener('DOMContentLoaded', (event) => {
    const qrReaderElement = document.getElementById('qr-reader');
    const resultsDiv = document.getElementById('qr-reader-results'); // For status messages
    const errorDiv = document.getElementById('scanErrorDisplay'); // Ensure error display exists

    if (qrReaderElement) {
        const config = {
            fps: 10,
            qrbox: (viewfinderWidth, viewfinderHeight) => {
                let minEdgePercentage = 0.7;
                let minEdgeSize = Math.min(viewfinderWidth, viewfinderHeight);
                let qrboxSize = Math.floor(minEdgeSize * minEdgePercentage);
                return { width: qrboxSize, height: qrboxSize };
            },
            facingMode: "environment",
            // Add supported formats to potentially slightly improve performance/accuracy
            formatsToSupport: [ Html5QrcodeSupportedFormats.QR_CODE ],
             rememberLastUsedCamera: true, // Good practice
             supportedScanTypes: [ // Prioritize camera
                 Html5QrcodeScanType.SCAN_TYPE_CAMERA,
                 Html5QrcodeScanType.SCAN_TYPE_FILE
             ]
        };

        // Create a new scanner instance and store it on the window object
        // This makes it globally accessible for the clear() call in onScanSuccess
        window.html5QrcodeScanner = new Html5QrcodeScanner(
            "qr-reader",
            config,
            /* verbose= */ false
        );

        // Clear any previous status/error messages
        if(resultsDiv) resultsDiv.innerHTML = 'Initializing scanner...';
        if(errorDiv) errorDiv.innerHTML = '';

        // Start scanning
        window.html5QrcodeScanner.render(onScanSuccess, onScanFailure);
        if(resultsDiv) resultsDiv.innerHTML = 'Scanner active. Position QR code in frame.';
        console.log("QR Scanner Initialized and Rendered.");

    } else {
        console.error("Error: Element with ID 'qr-reader' not found.");
        if(resultsDiv) resultsDiv.innerHTML = '<span style="color:red;">Error: Scanner UI element not found.</span>';
    }
});

// Optional: Add cleanup if user navigates away while scanner is active
window.addEventListener('beforeunload', () => {
    if (window.html5QrcodeScanner && typeof window.html5QrcodeScanner.getState === 'function' && window.html5QrcodeScanner.getState() === Html5QrcodeScannerState.SCANNING) {
         console.log("Attempting to stop scanner on page unload...");
         window.html5QrcodeScanner.clear().catch(err => console.error("Cleanup failed on page unload", err));
    }
});