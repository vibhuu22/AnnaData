"""
What the operator-notice filter must and must not swallow.

The two lists are not symmetric in importance. Letting a notice through costs
one model call. Dropping a farmer's question loses the only thing the service
exists to answer, and the farmer has already paid to send it - so the
FARMER_MESSAGES list is the one that matters, and it deliberately includes
phrasings that brush against the markers.

Run:  .venv/Scripts/python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from incoming_filter import is_operator_notice

# Traffic that should never reach the agent.
OPERATOR_MESSAGES = [
    # The notice that prompted this filter, verbatim from the backend log.
    "Dear Customer, You have a missed call from +919468739358 The last missed "
    "call was at 10:32 AM on 14-Sep-2026 Thankyou, Team Jio.",
    "Dear User, your recharge of Rs 239 is successful. Validity 28 days. Team Airtel",
    "123456 is your OTP for login. Do not share this OTP with anyone.",
    "Your A/c XX4321 is debited by Rs.2,000.00 on 02-Nov-26. Available balance Rs.15,230.00",
    "Dear Subscriber, your data pack of 1.5GB per day expires today. Recharge now.",
    "UPI Ref No 530212345678 processed successfully.",
    "Get 50% off on your next recharge! T&C apply. Click here to claim.",
    "Your validity expires on 05-Nov. Download the app to recharge instantly.",
    "To unsubscribe from these alerts reply STOPALERT",
]

# Real messages a farmer might send. None of these may be filtered.
FARMER_MESSAGES = [
    "hello",
    "kya haal",
    "acha bhai",
    "my wheat leaves are turning yellow",
    "gehu me pili patti aa rahi hai kya karu",
    "What is the MSP for mustard this year?",
    "mandi bhav batao kanpur ka",
    "How much urea per acre for wheat?",
    "मेरी गेहूं की फसल में पीलापन है",
    # Near-misses: farming words that brush against the markers.
    "my soil nutrient balance is poor, what should I add?",
    "I want to balance NPK in my field",
    "the shopkeeper did not share the price with me",
    "my tractor loan account needs papers, can I still get subsidy?",
    "I got a call from the KVK officer about my crop",
    "what pack size of DAP should I buy?",
    "is there any offer on seeds this season",
]


class TestOperatorNotices(unittest.TestCase):
    def test_operator_traffic_is_filtered(self):
        for msg in OPERATOR_MESSAGES:
            with self.subTest(msg=msg[:50]):
                self.assertTrue(
                    is_operator_notice(msg),
                    f"should have been filtered: {msg[:70]!r}",
                )


class TestFarmerMessages(unittest.TestCase):
    def test_farmer_questions_pass_through(self):
        for msg in FARMER_MESSAGES:
            with self.subTest(msg=msg[:50]):
                self.assertFalse(
                    is_operator_notice(msg),
                    f"a farmer's message was wrongly filtered: {msg[:70]!r}",
                )


class TestEdges(unittest.TestCase):
    def test_empty_and_none_are_not_notices(self):
        # An empty body is handled earlier in process_sms; the filter must not
        # claim it, so the existing "empty message" path keeps reporting it.
        self.assertFalse(is_operator_notice(""))
        self.assertFalse(is_operator_notice(None))
        self.assertFalse(is_operator_notice("   "))

    def test_matching_is_case_insensitive(self):
        self.assertTrue(is_operator_notice("DEAR CUSTOMER, YOU HAVE A MISSED CALL"))
        self.assertTrue(is_operator_notice("dear customer, you have a missed call"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
