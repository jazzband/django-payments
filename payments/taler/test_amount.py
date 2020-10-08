#  This file is part of TALER
#  (C) 2017 Taler Systems SA
#
#  This library is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2.1 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
#
#  @author Marcello Stanisci
#  @version 0.0
#  @repository https://git.taler.net/copylib.git/
#  This code is "copylib", it is versioned under the Git repository
#  mentioned above, and it is meant to be manually copied into any project
#  which might need it.

from __future__ import unicode_literals
from .amount import Amount, BadAmount
from unittest import TestCase
import json
from mock import MagicMock

class TestAmount(TestCase):
    def setUp(self):
        self.amount = Amount('TESTKUDOS')

    def test_parse_and_cmp(self):
        a = self.amount.parse('TESTKUDOS:0.0')
        self.assertEqual(Amount.cmp(self.amount, a), 0)
        b = self.amount.parse('TESTKUDOS:0.1')
        self.assertEqual(Amount.cmp(Amount('TESTKUDOS', fraction=10000000), b), 0)
        c = self.amount.parse('TESTKUDOS:3.3')
        self.assertEqual(Amount.cmp(Amount('TESTKUDOS', 3, 30000000), c), 0)
        self.assertEqual(Amount.cmp(a, b), -1)
        self.assertEqual(Amount.cmp(c, b), 1)
        with self.assertRaises(BadAmount):
            Amount.parse(':3')

    def test_add_and_dump(self):
        mocky = MagicMock()
        self.amount.add(Amount('TESTKUDOS', 9, 10**8))
        mocky(**self.amount.dump())
        mocky.assert_called_with(currency='TESTKUDOS', value=10, fraction=0)

    def test_subtraction(self):
        with self.assertRaises(ValueError):
            self.amount.subtract(Amount('TESTKUDOS', fraction=1))
        a = Amount('TESTKUDOS', 2)
        a.subtract(Amount('TESTKUDOS', 1, 99999999))
        self.assertEqual(Amount.cmp(a, Amount('TESTKUDOS', fraction=1)), 0)

    def test_stringify(self):
        self.assertEqual(self.amount.stringify(3), 'TESTKUDOS:0.000')
        self.amount.add(Amount('TESTKUDOS', 2, 100))
        self.assertEqual(self.amount.stringify(6), 'TESTKUDOS:2.000001')
