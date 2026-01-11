# Contributing to macPerplex

Thank you for your interest in contributing to macPerplex! This document provides guidelines for contributing to the project.

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/macPerplex.git
   cd macPerplex
   ```
3. **Set up development environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

## Development Setup

### Requirements
- macOS (required for screen capture and accessibility features)
- Python 3.10 or higher
- Chrome browser
- OpenAI API key

### Configuration
1. Copy `config.py.example` to `config.py`
2. Add your OpenAI API key
3. Configure trigger keys (default: F13/F14 for pedals, or cmd_r/shift_r for keyboard)

## Making Changes

### Before You Start
- Check existing [issues](https://github.com/sunnypsmith/macPerplex/issues) to see if someone else is working on something similar
- For major changes, open an issue first to discuss your approach

### Code Style
- Follow PEP 8 guidelines
- Use meaningful variable and function names
- Add docstrings to new functions
- Keep lines under 100 characters
- Use Rich console for user-facing output

### Testing
While we don't have automated tests yet, please manually test:
- Your changes don't break existing functionality
- Both pedal modes (screenshot+audio and audio-only) work
- Region selection overlay appears on all monitors
- Permission checks pass
- Perplexity integration works end-to-end

## Submitting Changes

### Pull Request Process
1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. **Make your changes** with clear, descriptive commits
3. **Update documentation** if needed (README.md, CHANGELOG.md)
4. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```
5. **Open a Pull Request** with:
   - Clear description of the changes
   - Reference to any related issues
   - Screenshots/videos if UI changes are involved

### Commit Messages
- Use clear, descriptive commit messages
- Start with a verb (Add, Fix, Update, Remove, etc.)
- Reference issue numbers when applicable

Example:
```
Add support for custom audio sample rates

- Allow users to configure sample rate in config.py
- Update README with new configuration option
- Fixes #123
```

## Reporting Issues

### Bug Reports
When reporting bugs, please include:
- macOS version
- Python version
- Steps to reproduce
- Expected vs actual behavior
- Error messages or screenshots
- Relevant configuration (with API keys removed)

### Feature Requests
For new features:
- Describe the problem you're trying to solve
- Explain your proposed solution
- Consider edge cases and user experience

## Code of Conduct

### Our Standards
- Be respectful and inclusive
- Welcome newcomers and help them learn
- Focus on constructive feedback
- Respect differing viewpoints and experiences

### Unacceptable Behavior
- Harassment or discriminatory language
- Trolling or insulting comments
- Personal or political attacks
- Publishing others' private information

## Questions?

If you have questions:
- Check the [README](README.md) and [documentation](README.md)
- Search existing [issues](https://github.com/sunnypsmith/macPerplex/issues)
- Open a new issue with the "question" label

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to macPerplex! 🎉

