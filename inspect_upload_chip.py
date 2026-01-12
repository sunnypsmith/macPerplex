#!/usr/bin/env python3
"""
Inspector script to find the upload chip/preview element on Perplexity.

This script monitors the DOM to identify what element appears after
uploading a file, so we can wait for it instead of using arbitrary delays.

Usage:
1. Make sure Chrome is running with remote debugging (same as macPerplex)
2. Have Perplexity.ai open
3. Run: python3 inspect_upload_chip.py
4. The script will take a snapshot of current elements
5. Upload a file to Perplexity manually
6. The script will show what NEW elements appeared
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time

def inspect_upload_chip():
    """Monitor for upload chip/preview elements."""
    
    print("="*60)
    print("🔍 Perplexity Upload Chip Inspector")
    print("="*60)
    
    # Connect to Chrome
    chrome_options = Options()
    chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        print(f"✓ Connected to Chrome")
        print(f"  Current URL: {driver.current_url}")
        
        # Find Perplexity tab
        current_handle = driver.current_window_handle
        perplexity_handle = None
        
        # Check if current tab is Perplexity
        if 'perplexity.ai' in driver.current_url:
            perplexity_handle = current_handle
            print("✓ Already on Perplexity tab")
        else:
            # Search through all tabs
            print("  Searching for Perplexity tab...")
            for handle in driver.window_handles:
                try:
                    driver.switch_to.window(handle)
                    if 'perplexity.ai' in driver.current_url:
                        perplexity_handle = handle
                        print(f"✓ Found Perplexity tab: {driver.current_url}")
                        break
                    else:
                        driver.switch_to.window(current_handle)
                except:
                    continue
        
        if not perplexity_handle:
            print("\n❌ Could not find Perplexity tab!")
            print("   Please open https://www.perplexity.ai in Chrome")
            return
        
        # Make sure we're on the Perplexity tab
        driver.switch_to.window(perplexity_handle)
        
        print("\n" + "="*60)
        print("Taking snapshot of CURRENT elements...")
        print("="*60)
        
        # Get baseline - all current elements with certain characteristics
        baseline_elements = set()
        
        # Potential upload indicator selectors
        selectors = [
            ("XPATH", "//img"),
            ("XPATH", "//div[contains(@class, 'preview')]"),
            ("XPATH", "//div[contains(@class, 'attachment')]"),
            ("XPATH", "//div[contains(@class, 'file')]"),
            ("XPATH", "//div[contains(@class, 'upload')]"),
            ("XPATH", "//div[contains(@class, 'image')]"),
            ("XPATH", "//button[contains(@aria-label, 'Remove')]"),
            ("XPATH", "//button[contains(@aria-label, 'Delete')]"),
            ("XPATH", "//button[contains(., '×')]"),
            ("XPATH", "//*[contains(@class, 'chip')]"),
            ("XPATH", "//*[contains(@class, 'tag')]"),
            ("XPATH", "//*[contains(@data-testid, 'upload')]"),
            ("XPATH", "//*[contains(@data-testid, 'attachment')]"),
        ]
        
        for selector_type, selector in selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for elem in elements:
                    try:
                        # Create unique identifier
                        elem_id = f"{elem.tag_name}:{elem.get_attribute('class')}:{elem.get_attribute('id')}"
                        baseline_elements.add(elem_id)
                    except:
                        pass
            except:
                pass
        
        print(f"✓ Captured {len(baseline_elements)} baseline elements")
        
        print("\n" + "="*60)
        print("⏸️  NOW UPLOAD A FILE TO PERPLEXITY")
        print("="*60)
        print("1. Click the chat input")
        print("2. Upload an image (use the paperclip/attach button)")
        print("3. Wait for the preview/chip to appear")
        print("4. Press Enter here when you see the upload chip...")
        print()
        input("Press Enter after uploading... ")
        
        print("\n" + "="*60)
        print("Scanning for NEW elements that appeared...")
        print("="*60)
        
        # Give it a moment to settle
        time.sleep(1)
        
        new_elements_found = []
        
        for selector_type, selector in selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for elem in elements:
                    try:
                        # Create unique identifier
                        elem_id = f"{elem.tag_name}:{elem.get_attribute('class')}:{elem.get_attribute('id')}"
                        
                        # Check if this is new
                        if elem_id not in baseline_elements:
                            # This is a NEW element!
                            if elem.is_displayed():  # Only care about visible ones
                                new_elements_found.append({
                                    'selector': selector,
                                    'element': elem,
                                    'elem_id': elem_id
                                })
                    except:
                        pass
            except:
                pass
        
        if not new_elements_found:
            print("\n❌ No new elements found!")
            print("   Either:")
            print("   - Upload didn't work")
            print("   - Element already existed (try on fresh page)")
            print("   - Need different selectors")
        else:
            print(f"\n✅ Found {len(new_elements_found)} NEW element(s)!")
            print("\nThese elements appeared after upload:")
            
            for idx, item in enumerate(new_elements_found[:10]):  # Show first 10
                elem = item['element']
                print(f"\n{'='*60}")
                print(f"NEW Element #{idx + 1}:")
                print(f"{'='*60}")
                print(f"  Original Selector: {item['selector']}")
                
                try:
                    print(f"  Tag: {elem.tag_name}")
                    print(f"  Text: {elem.text[:100] if elem.text else '(empty)'}")
                    print(f"  Visible: {elem.is_displayed()}")
                    
                    # Get useful attributes
                    attrs = ['class', 'id', 'src', 'alt', 'aria-label', 'data-testid', 
                            'role', 'type', 'data-state']
                    
                    for attr in attrs:
                        value = elem.get_attribute(attr)
                        if value:
                            print(f"  {attr}: {value[:150]}")
                    
                    # Try to build more specific selector
                    classes = elem.get_attribute('class')
                    elem_id = elem.get_attribute('id')
                    if elem_id:
                        specific_selector = f"//{elem.tag_name}[@id='{elem_id}']"
                        print(f"\n  ✨ Suggested selector: {specific_selector}")
                    elif classes:
                        # Use first class
                        first_class = classes.split()[0] if classes.split() else None
                        if first_class:
                            specific_selector = f"//{elem.tag_name}[contains(@class, '{first_class}')]"
                            print(f"\n  ✨ Suggested selector: {specific_selector}")
                    
                except Exception as e:
                    print(f"  Error getting details: {e}")
        
        print("\n" + "="*60)
        print("💡 Next Steps:")
        print("="*60)
        print("1. Find the element that reliably appears after upload")
        print("2. Note its selector (preferably with unique ID or class)")
        print("3. Use WebDriverWait for that element instead of sleep loop")
        print("4. This makes upload feel instant!")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        print("\nMake sure:")
        print("  - Chrome is running with remote debugging")
        print("  - You're on perplexity.ai")

if __name__ == "__main__":
    inspect_upload_chip()

