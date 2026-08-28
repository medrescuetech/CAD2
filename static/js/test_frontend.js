// Test script to identify frontend issues
console.log('Running frontend test script...');

// Test 1: Check if showAlert function exists
const testShowAlert = () => {
    console.log('Test 1: Checking if showAlert function exists');
    if (typeof showAlert === 'function') {
        console.log('✅ showAlert function exists');
    } else {
        console.error('❌ showAlert function does not exist but is referenced in error_handler.js and utils.js');
    }
};

// Test 2: Check if Utils object is properly initialized
const testUtils = () => {
    console.log('Test 2: Checking Utils initialization');
    if (typeof Utils === 'object') {
        console.log('✅ Utils object exists');
        // Try to use a method
        try {
            const formattedDate = Utils.formatTimestamp(new Date().toISOString());
            console.log(`✅ Utils.formatTimestamp works: ${formattedDate}`);
        } catch (e) {
            console.error('❌ Error using Utils.formatTimestamp:', e);
        }
    } else {
        console.error('❌ Utils object does not exist');
    }
};

// Test 3: Check if window.errorHandler is initialized
const testErrorHandler = () => {
    console.log('Test 3: Checking errorHandler initialization');
    if (window.errorHandler) {
        console.log('✅ errorHandler object exists');
        try {
            // Try using the handleError method with a test error
            window.errorHandler.handleError('Test Error', { message: 'This is a test error' });
            console.log('✅ errorHandler.handleError method called');
        } catch (e) {
            console.error('❌ Error using errorHandler.handleError:', e);
        }
    } else {
        console.error('❌ errorHandler object does not exist');
    }
};

// Test 4: Check APP_CONFIG initialization
const testAppConfig = () => {
    console.log('Test 4: Checking APP_CONFIG initialization');
    if (window.APP_CONFIG) {
        console.log('✅ APP_CONFIG exists:', window.APP_CONFIG);
    } else {
        console.error('❌ APP_CONFIG does not exist');
    }
};

// Run tests when document is ready
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM Content Loaded - Running tests...');
    testShowAlert();
    testUtils();
    testErrorHandler();
    testAppConfig();
    
    // Add a UI element to show test results
    const resultDiv = document.createElement('div');
    resultDiv.style.position = 'fixed';
    resultDiv.style.top = '10px';
    resultDiv.style.right = '10px';
    resultDiv.style.padding = '10px';
    resultDiv.style.background = 'rgba(0,0,0,0.8)';
    resultDiv.style.color = 'white';
    resultDiv.style.zIndex = '9999';
    resultDiv.style.borderRadius = '5px';
    resultDiv.innerHTML = 'Frontend tests complete. Check console for results.';
    document.body.appendChild(resultDiv);
});
