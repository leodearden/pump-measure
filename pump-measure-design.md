## pump-measure.py

Pump measure uses direct control of the pumps and access to mass readings from a top pan balance to measure the behaviour of the pumps under test.

### set up phase

0. Connect the pumps to the pump control electronics.
1. Connect the pump control electronics to the test host.
1. Connect the top pan balance serial port to the test host.
1. Configure the top pan balance to send mass readings via the serial port at maximum rate.
1. Calibrate the top pan balance.
1. Place a beaker on the balance, and tare.
1. Connect one side of the pumps to a fluid reservoir.
1. Connect the other side of the pumps to a hose suspended near the bottom of (but not touching) the beaker on the balance.
1. Log in to the test host.
1. Prime the pumps:
  1. Open all the pump output ports.
  1. Use pronsole.py (part of the Printrun suite) to instruct the pumps to prime (by pumping a few hundred revolutions at maximum rate).
  1. Visually inspect all the hoses for bubbles.
  1. Pump some fluid back and forth, and inspect again for bubbles.
1. Repeat priming as required, taking care to reverse direction before the beaker on the balance is emptied or overfilled, until the hoses are visibly bubble free.  

Close all output ports.

### test procedure (all performed automatically by the script)

Given a list of feed rates (in rpm) and amounts (numbers of revolutions), generate a test matrix.

Given a maximum time for one pumping operation, discard all tests that would take more than that time to complete one operation. eg: If the max time is 61s, and the rates are (2, 3), and the revs are (1, 3), then 3 revs at 2rpm would be rejected (it would take 90s to complete, and 90s > 61s), and the other combinations would be accepted.

For each accepted pair of test parameters:

First initialise the test system by pumping fluid to bring the contents of the beaker near to a target initial mass (eg: 111g), and then record UTC (universal time).

Then, take a number of pairs of filling and empyting measurements (by default, 11) with that pair of parameters. Each filling measurement is taken by performing the following steps:

1. Discard any stale data from the top pan balance (as received via the serial port).
1. Instruct the pumps to begin turning the specified number of revolutions at the specified rate, in the direction that will put fluid into the beaker.
1. Collect mass readings continuously for long enough for the pumping operation to complete and then for the balance to stabilise.
1. Record the difference between the maximum reading and the minimum reading as the mass moved by the pump during that operation.

After a filling measurement has been taken an emptying measurement is taken by repeating these steps, except moving the pump in the opposite direction.
