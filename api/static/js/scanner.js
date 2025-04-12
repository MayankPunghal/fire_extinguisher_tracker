// static/js/scanner.js

/**
 * Handles the successful scan of a QR code.
 * @param {string} decodedText - The decoded text from the QR code (expected to be a URL).
 * @param {object} decodedResult - Detailed information about the scan result.
 */
// Example assuming a scanner library that gives you 'decodedText'
function onScanSuccess(decodedText, decodedResult) {
    console.log(`Raw QR Code Text: ${decodedText}`);

    let parsedData;
    try {
            // --- DECIDE WHAT TO DO ---
            // Option A: Always go to the check-in page (like before)
            const checkUrl = window.location.origin + '/check/' + decodedText;
            console.log(`Redirecting to Check-in: ${checkUrl}`);

            // Option B: Go to the view page
            // const viewUrl = window.location.origin + '/extinguisher/' + extinguisherId;
            // console.log(`Redirecting to View: ${viewUrl}`);

            // Optional: Display some scanned info on the current page before redirecting
            // if (parsedData.sn) {
            //     document.getElementById('scannedInfoDisplay').textContent = `Scanned SN: ${parsedData.sn}, Loc: ${parsedData.loc || 'N/A'}`;
            // }

            // Stop the scanner (replace with your specific scanner object/method)
            // html5QrcodeScanner.clear().catch(error => console.error("Failed to clear scanner", error));

            // --- REDIRECT (Choose Option A or B URL) ---
             window.location.href = checkUrl; // Using Option A here

        }
        catch (error) {
        console.error("Failed to parse QR code JSON:", error);
        console.error("Scanned text was:", decodedText);
        // Display error to user - maybe the QR wasn't JSON?
        displayScanError('Error reading QR Code data. Is it the correct format?');
    }
}

// Helper to display errors on the scan page (create an element with id="scanErrorDisplay")
function displayScanError(message) {
    const errorElement = document.getElementById('scanErrorDisplay'); // Make sure this element exists in scan.html
    if (errorElement) {
        errorElement.textContent = message;
        errorElement.style.color = 'red';
    }
}

// --- Make sure your scanner library setup calls onScanSuccess ---
// html5QrcodeScanner.render(onScanSuccess, onScanFailure);

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