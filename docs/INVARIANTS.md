1. A submission is processed at most once logically.

2. A retry must never duplicate successful delivery.

3. The LLM never decides or modifies classification.

4. Client reports never contain internal assessment metadata.

5. Internal reports may contain client-facing information;
   client reports may not contain internal-only information.

6. Every classification must be explainable by triggered rules.

7. Raw form submissions are immutable.

8. Business-rule changes require a new rule version.

9. Model/provider changes cannot alter deterministic classification.

10. Reports must never contain facts absent from either:
    a) the form response, or
    b) deterministic rule output.

11. External service failure cannot cause data loss.

12. Secrets are never committed or logged.

13. Sensitive form data is never written to application logs.

14. No email is sent until the associated artifact is successfully generated.

15. A completed submission can be reconstructed from stored metadata.