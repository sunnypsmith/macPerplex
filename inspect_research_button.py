#!/usr/bin/env python3
"""
Inspector script to find the Deep Research button on Perplexity.

This script connects to Chrome and helps identify the correct selector
for the Deep Research button and its state.

Usage:
1. Make sure Chrome is running with remote debugging (same as macPerplex)
2. Have Perplexity.ai open
3. Run: python3 inspect_research_button.py
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time

def inspect_research_button():
    """Find and inspect the Deep Research button."""
    
    print("="*60)
    print("🔍 Perplexity Deep Research Button Inspector")
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
        print("Searching for Deep Research button...")
        print("="*60)
        
        # Try different possible selectors
        selectors = [
            ("XPATH", "//button[@aria-label='Research' and @role='radio']"),  # Most specific
            ("XPATH", "//button[contains(., 'Deep')]"),
            ("XPATH", "//button[contains(., 'Research')]"),
            ("XPATH", "//button[contains(@aria-label, 'Deep')]"),
            ("XPATH", "//button[contains(@aria-label, 'Research')]"),
            ("XPATH", "//button[contains(@aria-label, 'research')]"),
            ("XPATH", "//button[contains(text(), 'Deep')]"),
            ("CSS", "button[aria-label*='Deep']"),
            ("CSS", "button[aria-label*='Research']"),
            ("CSS", "button[aria-label*='research']"),
            ("XPATH", "//*[contains(@class, 'research')]"),
            ("XPATH", "//*[contains(@class, 'deep')]"),
        ]
        
        found_buttons = []
        
        for selector_type, selector in selectors:
            try:
                if selector_type == "XPATH":
                    elements = driver.find_elements(By.XPATH, selector)
                else:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                
                if elements:
                    print(f"\n✓ Found {len(elements)} element(s) with: {selector}")
                    
                    for idx, elem in enumerate(elements):
                        if elem not in found_buttons:
                            found_buttons.append(elem)
                            print(f"\n  Element #{len(found_buttons)}:")
                            
                            # Get all useful attributes
                            try:
                                print(f"    Tag: {elem.tag_name}")
                                print(f"    Text: {elem.text[:100] if elem.text else '(empty)'}")
                                print(f"    Visible: {elem.is_displayed()}")
                                print(f"    Enabled: {elem.is_enabled()}")
                                
                                # Common attributes
                                attrs = ['aria-label', 'aria-pressed', 'aria-checked', 'role', 
                                        'class', 'id', 'type', 'data-state', 'data-testid']
                                
                                for attr in attrs:
                                    value = elem.get_attribute(attr)
                                    if value:
                                        print(f"    {attr}: {value[:100]}")
                                
                                # Get computed styles
                                try:
                                    bg_color = driver.execute_script(
                                        "return window.getComputedStyle(arguments[0]).backgroundColor;", 
                                        elem
                                    )
                                    print(f"    Background color: {bg_color}")
                                except:
                                    pass
                                
                            except Exception as e:
                                print(f"    Error getting details: {e}")
            
            except Exception as e:
                pass  # Selector didn't work
        
        if not found_buttons:
            print("\n❌ No Deep Research button found!")
            print("\nTrying broader search for all buttons...")
            
            all_buttons = driver.find_elements(By.TAG_NAME, "button")
            print(f"\n✓ Found {len(all_buttons)} total buttons on page")
            print("\nButtons with interesting text/labels:")
            
            for idx, btn in enumerate(all_buttons):
                try:
                    text = btn.text.strip()
                    aria_label = btn.get_attribute('aria-label') or ''
                    
                    # Look for anything research-related or interesting
                    if any(word in (text + aria_label).lower() for word in 
                           ['deep', 'research', 'pro', 'advanced', 'mode']):
                        print(f"\n  Button #{idx}:")
                        print(f"    Text: {text[:80]}")
                        print(f"    aria-label: {aria_label[:80]}")
                        print(f"    Visible: {btn.is_displayed()}")
                        print(f"    class: {btn.get_attribute('class')[:80]}")
                except:
                    pass
        
        print("\n" + "="*60)
        print("💡 Next Steps:")
        print("="*60)
        print("1. Review the elements above")
        print("2. Note the selector that works (XPATH or CSS)")
        print("3. Note how to detect if button is ON (aria-pressed, class, etc.)")
        print("4. Use this info to add the feature to macPerplex.py")
        print("\nPress Ctrl+C when done inspecting")
        print("="*60)
        
        # Keep connection open for manual inspection
        input("\nPress Enter to exit...")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure:")
        print("  - Chrome is running with remote debugging")
        print("  - You're on perplexity.ai")

if __name__ == "__main__":
    inspect_research_button()

