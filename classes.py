import pandas as pd
from datetime import date


class Person:
    def __init__(self, age, income, spending_strategy, generosity_strategy):
        self.age = age
        self.income = income
        self.spending_strategy = spending_strategy
        self.generosity_strategy = generosity_strategy
        self.giving_tracker = SpendingTracker()
        self.investments = {
            "Retirement": Investment("Retirement", 1.1, tax_free=True),  # roth
            "Giving": Investment("Giving", 1.1),
            "Additional Investments": [],
        }


class PortfolioManager:
    def __init__(
        self,
        spendstrat,
        genstrat,
        salary,
    ):
        self.spendstrat = spendstrat
        self.genstrat = genstrat
        self.salary = salary
        self.ia = InflationAdjuster(0.04)
        self.tax_cal = TaxCalculator()
        self.taxes_ytd_ia = {}
        self.income_ytd = {}
        # NOTE: a 0.096 growth rate (compounded monthly) is equivalent to 10% growth rate (compounded annually)
        self.retirement_investment = Investment("Retirement", 0.096, tax_free=True)
        self.giving_investment = Investment("Giving", 0.096)
        self.giving_tracker = SpendingTracker()
        self.assets = []
        self.asset_savings = Investment("Asset Savings", 0.096)
        self.df = pd.DataFrame(
            {
                "Salary": [salary.salary],
                "Total Income": [salary.salary],
                "Retirement Savings": [0],
                "Giving Savings": [0],
                "Asset Savings": [0],
                "years_from_start": [0],
                "Total Giving": [0],
            }
        )

    def _get_paid(self, years_from_start: float):
        salary_paycheck = round(self.salary.get_paid(), 2)
        assets_income = sum([asset.pay_dividend() for asset in self.assets])

        total_income = salary_paycheck + assets_income
        # adjust for inflation annually instead of monthly, is more intuitive - adjust X years back
        n_years = int(years_from_start)
        ia_income = round(self.ia.reverse_adjust(total_income, n_years), 2)
        fraction = years_from_start % 1
        current_month = int(fraction * 12) + 1

        self.tax_cal.add_inflation_adjusted_income(ia_income, current_month)
        tax_rate = self.tax_cal.get_tax_rate(current_month)

        self.taxes_ytd_ia[current_month] = ia_income * tax_rate

        # if 12th month of year, get tax return
        if current_month == 12:
            tax_return = self._get_tax_return()
            total_income += tax_return

        self.income_ytd[current_month] = ia_income
        return total_income * (1 - tax_rate)

    def _manage_income(self, income, years_from_start):
        (
            base_spending,
            retirement_saving,
            disp_spend,
            disp_invest,
            disp_give,
        ) = self.spendstrat.base_retirement_spend_invest_give(income)

        # -----------handle giving-----------
        spend_give, invest_give = self.genstrat.straight_invest(disp_give)
        draw_down_rate = self.genstrat.investment_draw_down_rate
        withdrawal = self.giving_investment.total * draw_down_rate

        self.giving_investment.withdraw_accounting_for_taxes(
            withdrawal, years_from_start
        )
        self.giving_investment.add(invest_give, years_from_start)

        self.giving_tracker.add(spend_give, years_from_start)
        self.giving_tracker.add(withdrawal, years_from_start)

        # -----------handle investing-----------
        self.retirement_investment.add(retirement_saving, years_from_start)

        # -----------determine n assets to purchase-----------
        n_assets = 0
        asset_price = self.ia.forward_adjust(150000, years_from_start)
        if disp_invest >= asset_price:
            n_assets = int(disp_invest / asset_price)
            disp_invest -= n_assets * asset_price

        if self.asset_savings.test_sufficient_funds(asset_price - disp_invest):
            # purchase asset
            self.asset_savings.withdraw_accounting_for_taxes(
                asset_price - disp_invest, years_from_start
            )
            n_assets += 1

        if n_assets == 0:
            self.asset_savings.add(disp_invest, years_from_start)

        else:
            self._purchase_assets(n_assets, asset_price)

    def _purchase_assets(self, n_assets, asset_price):
        for i in range(n_assets):
            current_assets = len(self.assets)
            new_asset_name = f"Asset {current_assets+i}+1"
            # 3.8% = avg appreciation US / year, 1% of total value is average rent
            new_asset = Asset(
                name=new_asset_name,
                value=asset_price,
                growth_rate=0.036,
                dividend_rate=0.01,
            )
            self.assets.append(new_asset)
            raise ValueError("Need to remove from investments still")

    def _grow_investments_and_assets(self, years_from_start, current_month):
        self.retirement_investment.grow(years_from_start)
        self.giving_investment.grow(years_from_start)
        self.asset_savings.grow(years_from_start)
        # only update assets once / year (to replicate rent not rising every month)
        if current_month == 12:
            for asset in self.assets:
                # have to now account for the whole year
                assets.grow(years_from_start)

    def _get_tax_return(self):
        sum_taxes = sum(self.taxes_ytd_ia.values())
        return self.tax_cal.get_tax_return(sum_taxes)

    def _close_out_year(self):
        self.tax_cal.reset_year()
        self.taxes_ytd_ia = {}
        self.salary.get_raise(1.05)

    def init_retirement_savings(self, amount):
        self.retirement_investment.add(amount, 0)
        self.df.iloc[0, self.df.columns.get_loc("Retirement Savings")] = amount

    def init_giving_savings(self, amount):
        self.giving_investment.add(amount, 0)
        self.df.iloc[0, self.df.columns.get_loc("Giving Savings")] = amount

    def simulate_month(self, years_from_start):
        fraction = years_from_start % 1
        current_month = int(fraction * 12) + 1
        # get paid
        income = self._get_paid(years_from_start)
        # manage income
        self._manage_income(income, years_from_start)
        # grow investments

        self._grow_investments_and_assets(years_from_start, current_month)
        # close out year
        if current_month == 12:
            self._close_out_year()
            # update df
            self._update_df(years_from_start)

    def _update_df(self, years_from_start):
        new_row = pd.DataFrame(
            {
                "Salary": [self.salary.salary],
                "Total Income": [sum(self.income_ytd.values())],
                "Retirement Savings": [self.retirement_investment.total],
                "Giving Savings": [self.giving_investment.total],
                "Asset Savings": [self.asset_savings.total],
                "years_from_start": [years_from_start],
                "Total Giving": [self.giving_tracker.total],
            }
        )
        self.df = pd.concat([self.df, new_row], ignore_index=True)


class SpendingStrategy:
    def __init__(
        self,
        base_spending: float,
        retirement_saving: float,
        disp_spend: float,
        disp_give: float,
    ):
        self.base_spending = base_spending
        self.retirement_saving = retirement_saving
        self.disposible_spending = 1 - base_spending - retirement_saving
        self.disp_spend = disp_spend
        self.disp_give = disp_give
        self.disp_invest = 1 - disp_spend - disp_give

    def base_retirement_spend_invest_give(self, paycheck):
        return (
            paycheck * self.base_spending,
            paycheck * self.retirement_saving,
            paycheck * self.disposible_spending * self.disp_spend,
            paycheck * self.disposible_spending * self.disp_invest,
            paycheck * self.disposible_spending * self.disp_give,
        )


class GenerosityStrategy:
    def __init__(
        self,
        straight_percent: float,
        investment_draw_down_rate: float,
        legacy_give_percent: float,
    ):
        self.straight_percent = straight_percent
        self.investment_percent = 1 - straight_percent
        self.investment_draw_down_rate = investment_draw_down_rate / 12
        self.legacy_give_percent = legacy_give_percent

    def straight_invest(self, paycheck):
        return paycheck * self.straight_percent, paycheck * self.investment_percent


class InflationAdjuster:
    def __init__(self, inflation_rate):
        self.inflation_rate = inflation_rate

    def reverse_adjust(self, amount, years):
        return amount * (1 - self.inflation_rate) ** years

    def forward_adjust(self, amount, years):
        return amount * (1 + self.inflation_rate) ** years


class TaxCalculator:
    tax_brackets = {
        (22001, 89450): 0.12,
        (89451, 190750): 0.22,
        (190751, 364200): 0.24,
        (364201, 462500): 0.32,
        (462501, 693750): 0.35,
        (693751, 9999999): 0.37,
    }
    capital_gains = 0.15

    def __init__(self):
        self.year_to_date = {}
        self.projected_inflation_adjusted_income = {}

    def reset_year(self):
        self.year_to_date = {}
        self.projected_inflation_adjusted_income = {}

    def add_inflation_adjusted_income(self, ia_income: float, current_month: int):
        self.year_to_date[current_month] = ia_income
        sum_income = sum(self.year_to_date.values())
        self.projected_inflation_adjusted_income[current_month] = (
            sum_income / (current_month / 12) - 29200  # standard deduction
        )

    def get_tax_rate(self, current_month):
        tax = 0
        for (lower, upper), rate in self.tax_brackets.items():
            if (
                lower
                <= self.projected_inflation_adjusted_income[current_month]
                <= upper
            ):
                return rate
        raise ValueError(f"Invalid income: {self.projected_inflation_adjusted_income}")

    def get_tax_return(self, total_taxes_paid: float):
        tax_rate = self.get_tax_rate(current_month=12)
        total_taxes = self.projected_inflation_adjusted_income[12] * tax_rate
        return total_taxes_paid - total_taxes


class SpendingTracker:
    def __init__(self):
        self.df = pd.DataFrame({"Spending": [], "Total": [], "years_from_start": []})
        self.total = 0

    def add(self, amount, years_from_start):
        self.total += amount
        new_row = pd.DataFrame(
            {
                "Spending": [amount],
                "Total": [self.total],
                "years_from_start": [years_from_start],
            }
        )
        self.df = pd.concat([self.df, new_row], ignore_index=True)


class Salary:
    def __init__(self, salary):
        self.salary = salary

    def get_paid(self):
        return self.salary / 12

    def get_raise(self, multiplier):
        self.salary *= multiplier


class Asset:
    # per chatGPT : all are percentages of house value except vacancy rate
    vacancy_rate = 0.0833  # 5-10%, this represents 1 month / year
    insurance = 0.0035
    taxes = 0.00730  # https://smartasset.com/taxes/tennessee-property-tax-calculator
    maintenance = 0.01

    def __init__(
        self,
        name,
        value,
        growth_rate,
        years_from_start,
        dividend_rate=None,
    ):
        self.name = name
        self.value = value
        self.growth_rate = growth_rate  # annual growth rate
        self.dividend_rate = dividend_rate
        # now subtract out expenses to estimate actual profitability
        self.profit_dividend_rate = (1 - self.vacancy_rate) * dividend_rate - (
            self.insurance + self.taxes + self.maintenance
        ) / 12  # (these last 3 are annualized)
        self.df = pd.DataFrame(
            {"Value": [value], "years_from_start": [years_from_start]}
        )

    def grow(self, years_from_start):
        most_recent_growth = self.df["years_from_start"].max()
        if years_from_start >= (most_recent_growth + 1):
            new_value = round(self.value * (1 + self.growth_rate), 2)
            new_row = pd.DataFrame(
                {
                    "Value": [new_value],
                    "years_from_start": [years_from_start],
                }
            )
            self.df = pd.concat([self.df, new_row], ignore_index=True)
            self.value = new_value

    def pay_dividend(self):
        if self.dividend_rate is None:
            raise ValueError("Dividend rate or frequency not set")
        return round(self.profit_dividend_rate * self.value, 2)


class Investment:
    def __init__(self, name, annual_growth_rate, tax_free=False):
        self.name = name
        self.growth_rate = 1 + (annual_growth_rate / 12)  # monthly growth rate
        self.tax_free = tax_free
        self.total = 0
        self.df = pd.DataFrame(
            {
                "Number Stocks": [],
                "Stock Cost": [],
                "Total Value": [],
                "years_from_start": [],
                "change_type": [],
            }
        )
        self.cost_basis = None
        self.stock_cost = 1  # init at $1 / stock
        self.nstocks = 0

    def add(self, amount, years_from_start):
        stocks_purchased = amount / self.stock_cost
        self._update_cost_basis(stocks_purchased)
        self.nstocks += stocks_purchased
        self.total = self.nstocks * self.stock_cost
        new_row = pd.DataFrame(
            {
                "Number Stocks": [self.nstocks],
                "Stock Cost": [self.stock_cost],
                "Total Value": [self.total],
                "years_from_start": [years_from_start],
                "change_type": ["add"],
            }
        )
        self.df = pd.concat([self.df, new_row], ignore_index=True)

    def _update_cost_basis(self, stocks_purchased):
        if self.cost_basis is None:
            self.cost_basis = self.stock_cost
        else:
            self.cost_basis = (
                self.cost_basis * self.nstocks + self.stock_cost * stocks_purchased
            ) / (self.nstocks + stocks_purchased)

    def grow(self, years_from_start):
        # first verify we haven't already grown this month
        grow_df = self.df[self.df["change_type"] == "grow"]
        if (
            grow_df["years_from_start"].max() < years_from_start
            or grow_df.shape[0] == 0
        ):
            self.stock_cost *= self.growth_rate
            self.total = self.nstocks * self.stock_cost
            new_row = pd.DataFrame(
                {
                    "Number Stocks": [self.nstocks],
                    "Stock Cost": [self.stock_cost],
                    "Total Value": [self.total],
                    "years_from_start": [years_from_start],
                    "change_type": ["grow"],
                }
            )
            self.df = pd.concat([self.df, new_row], ignore_index=True)

    def withdraw_accounting_for_taxes(self, amount, years_from_start, gains_rate=0.15):
        # did math on ipad and solved for n_stocks to withdraw post-tax amount
        # i.e. if we want to withdraw 1000 it will withdraw 1000 + enough to account for taxes such that 1000 is what you get post tax
        if self.tax_free:
            tax_rate = 0
        else:
            tax_rate = gains_rate

        stocks_to_sell = amount / (
            (1 - tax_rate) * self.stock_cost + tax_rate * self.cost_basis
        )
        self.nstocks -= stocks_to_sell
        self.total = self.nstocks * self.stock_cost
        new_row = pd.DataFrame(
            {
                "Number Stocks": [self.nstocks],
                "Stock Cost": [self.stock_cost],
                "Total Value": [self.total],
                "years_from_start": [years_from_start],
                "change_type": ["withdraw"],
            }
        )
        self.df = pd.concat([self.df, new_row], ignore_index=True)
        if self.tax_free:
            return 0
        else:
            return stocks_to_sell * (self.stock_cost - self.cost_basis)

    def test_sufficient_funds(self, amount, gains_rate=0.15):
        if self.tax_free:
            tax_rate = 0
        else:
            tax_rate = gains_rate

        if self.cost_basis == None:
            return False
        else:
            return amount <= self.nstocks * (
                (1 - tax_rate) * self.stock_cost + tax_rate * self.cost_basis
            )
