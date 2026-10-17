Feature: Multi-touch attribution credit
  As a performance marketer
  I want to see how each model divides a conversion
  So that I can tell signal from the platform's own reporting bias

  Scenario: First touch credits the channel that found the customer
    Given a two-step journey from "display" to "google" worth 100000 cents
    When I attribute it with the "first_touch" model
    Then "display" is credited 100000 cents
    And "google" is credited 0 cents

  Scenario: Last touch credits the channel that closed
    Given a two-step journey from "display" to "google" worth 100000 cents
    When I attribute it with the "last_touch" model
    Then "google" is credited 100000 cents
    And "display" is credited 0 cents

  Scenario: Linear splits the revenue and keeps every paisa
    Given a three-step journey from "display" to "meta" to "google" worth 100000 cents
    When I attribute it with the "linear" model
    Then "display" is credited 33334 cents
    And "meta" is credited 33333 cents
    And "google" is credited 33333 cents
    And the credited total is 100000 cents

  Scenario: Position based rewards discovery and closing equally
    Given a three-step journey from "display" to "meta" to "google" worth 100000 cents
    When I attribute it with the "position_based" model
    Then "display" is credited 40000 cents
    And "meta" is credited 20000 cents
    And "google" is credited 40000 cents
