// static/js/scanner.js

/**
 * Handles the successful scan of a QR code.
 * @param {string} decodedText - The decoded text from the QR code (expected to be a URL).
 * @param {object} decodedResult - Detailed information about the scan result.
 */
function onScanSuccess(decodedText, decodedResult) {
    // Log the scan result to the browser's developer console for debugging.
    console.log(`QR Code Scanned: ${decodedText}`, decodedResult);

    const resultsDiv = document.getElementById('qr-reader-results');

    // --- Core Logic: Check if the scanned text looks like our check-in URL ---
    // We expect URLs like: https://your-app.vercel.app/check/some-unique-id
    // A simple check for '/check/' is usually sufficient here.
    // For more robustness, you could use a Regular Expression or URL parsing.
    if (decodedText && decodedText.includes('/check/')) {
        resultsDiv.innerHTML = `Scan successful! Redirecting to: <a href="${decodedText}">${decodedText}</a>`;
        resultsDiv.style.color = 'green';

        // --- Stop Scanning ---
        // It's important to stop the scanner before redirecting,
        // otherwise, the camera might stay active briefly after navigation.
        // html5QrcodeScanner is accessible if declared outside this function scope (see below)
        if (window.html5QrcodeScanner && typeof window.html5QrcodeScanner.clear === 'function') {
             window.html5QrcodeScanner.clear().then(_ => {
                console.log("Scanner cleared successfully before redirect.");
                // --- Redirect the browser ---
                window.location.href = decodedText;
            }).catch(error => {
                console.error("Failed to clear scanner:", error);
                // Still attempt to redirect even if clearing fails
                window.location.href = decodedText;
            });
        } else {
             console.warn("Scanner instance not found or clear method unavailable. Redirecting anyway.");
             // --- Redirect the browser ---
             window.location.href = decodedText;
        }

    } else {
        // The scanned QR code doesn't contain the expected '/check/' path.
        console.warn("Scanned QR code does not appear to be a valid check-in URL:", decodedText);
        resultsDiv.innerHTML = `<span style="color:orange;">Scanned data is not a valid check-in link. Please scan an extinguisher QR code.</span>`;
        // Keep scanning...
    }
}

/**
 * Handles errors during the scanning process (e.g., no QR code found in frame).
 * @param {string} error - The error message.
 */
function onScanFailure(error) {
    // This function is called quite frequently when no QR code is found.
    // It's usually best to ignore these errors or provide minimal feedback,
    // otherwise the console/UI gets spammed.
    // console.warn(`QR Code scan error: ${error}`);

    // Optionally, provide subtle feedback to the user that scanning is active
    // const resultsDiv = document.getElementById('qr-reader-results');
    // resultsDiv.innerHTML = `Scanning...`; // Can be visually noisy
}

// --- Initialize the Scanner when the DOM is ready ---
document.addEventListener('DOMContentLoaded', (event) => {
    // Get the element where the scanner viewfinder will be rendered.
    const qrReaderElement = document.getElementById('qr-reader');
    const resultsDiv = document.getElementById('qr-reader-results');

    if (qrReaderElement) {
        // Configuration options for the scanner.
        // See https://github.com/mebjas/html5-qrcode#configuration
        const config = {
            fps: 10, // Frames per second to attempt scanning.
            qrbox: (viewfinderWidth, viewfinderHeight) => {
                // Calculate the size of the square scanning box.
                // Make it responsive, e.g., 70% of the smaller viewfinder dimension.
                let minEdgePercentage = 0.7;
                let minEdgeSize = Math.min(viewfinderWidth, viewfinderHeight);
                let qrboxSize = Math.floor(minEdgeSize * minEdgePercentage);
                return {
                    width: qrboxSize,
                    height: qrboxSize
                };
            },
            // Request the rear camera ("environment") if available.
            facingMode: "environment",
            // Optional: Can add experimental features if needed, but defaults are usually fine.
            // experimentalFeatures: {
            //     useBarCodeDetectorIfSupported: true
            // },
            // Optional: Only scan QR codes (can improve performance slightly if barcodes aren't needed)
            // formatsToSupport: [ Html5QrcodeSupportedFormats.QR_CODE ]
        };

        // Create a new scanner instance.
        // Store it on the window object to make it accessible in the success callback for clearing.
        window.html5QrcodeScanner = new Html5QrcodeScanner(
            "qr-reader", // ID of the element to render the scanner in.
            config,
            /* verbose= */ false // Set to true for detailed logs from the library.
        );

        // Start scanning. Pass the success and failure callback functions.
        resultsDiv.innerHTML = 'Initializing scanner... Requesting camera access...';
        window.html5QrcodeScanner.render(onScanSuccess, onScanFailure);
        resultsDiv.innerHTML = 'Scanner active. Position QR code in frame.';

    } else {
        console.error("Error: Element with ID 'qr-reader' not found in the DOM.");
        if(resultsDiv) {
            resultsDiv.innerHTML = '<span style="color:red;">Error: Scanner UI element not found.</span>';
        }
    }
});