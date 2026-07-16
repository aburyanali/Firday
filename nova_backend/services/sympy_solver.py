import re
import sympy as sp
from typing import Dict, Any, Optional
from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_multiplication_application

class SympySolver:
    """
    Production-grade SymPy Mathematical Solver for NOVA OS.
    Provides exact symbolic math validation, automatic simplification, 
    and strict LaTeX formatting blocks.
    """
    
    def __init__(self) -> None:
        self.x = sp.Symbol('x')
        self.y = sp.Symbol('y')
        self.transformations = standard_transformations + (implicit_multiplication_application,)

    def solve_expression(self, expression_text: str) -> Optional[Dict[str, str]]:
        """
        Parses, solves, simplifies, and mathematically validates standard expressions.
        Returns LaTeX formatted solver blocks or None if parsing fails.
        """
        try:
            cleaned = self._clean_input(expression_text)
            
            # 1. Integration Checks
            if any(k in cleaned for k in ["integrate", "integral", "∫"]):
                return self._solve_integral(cleaned)
                
            # 2. Derivative Checks
            if any(k in cleaned for k in ["diff", "derivative", "differentiate", "d/dx"]):
                return self._solve_derivative(cleaned)
                
            # 3. Limit Checks
            if "limit" in cleaned:
                return self._solve_limit(cleaned)
                
            # 4. Standard Equations (e.g. x^2 - 4 = 0 or solve x^2 + 5x + 6)
            if "solve" in cleaned or "=" in cleaned or any(op in cleaned for op in ["x**2", "x^2"]):
                return self._solve_equation(cleaned)
                
            # 5. Pure Arithmetic fallback (e.g. 11 * 11 or sqrt(144))
            return self._solve_arithmetic(cleaned)
            
        except Exception as e:
            # Let fallback route take over if SymPy fails
            return None

    def _clean_input(self, text: str) -> str:
        """Standardizes input mathematical notations for SymPy parsing."""
        text = text.lower().strip()
        # Remove wrapper question marks or words
        text = re.sub(r'\b(please|what is|whats|solve|calculate|evaluate|compute|find)\b', '', text)
        text = text.replace("?", "")
        text = text.replace(" ", "")
        # Map symbols to python expressions
        text = text.replace("²", "**2")
        text = text.replace("³", "**3")
        text = text.replace("^", "**")
        text = text.replace("×", "*")
        text = text.replace("÷", "/")
        return text

    def _solve_integral(self, text: str) -> Dict[str, str]:
        """Integrates expression, simplifies, and validates by differentiating the result."""
        # Extract integrand, e.g. from integrate(x**2) or ∫x**2dx
        integrand_str = self._extract_target(text, ["integrate", "integral", "∫"])
        integrand_expr = self._parse(integrand_str)
        
        # Perform integration
        result = sp.integrate(integrand_expr, self.x)
        
        # Verify correctness: differentiate the result
        derivative = sp.diff(result, self.x)
        verified = sp.simplify(derivative - integrand_expr) == 0
        
        if not verified:
            raise ValueError("Integration verification failed.")
            
        problem_latex = sp.latex(sp.Integral(integrand_expr, self.x))
        result_latex = sp.latex(result)
        
        return {
            "problem": f"\\int {sp.latex(integrand_expr)} \\, dx",
            "steps": (
                f"- Identifed integration target: $$ f(x) = {sp.latex(integrand_expr)} $$.\n"
                f"- Evaluated antiderivative symbolically using standard integration algorithms.\n"
                f"- Mathematically verified correctness by differentiating: $$ \\frac{{d}}{{dx}} \\left( {result_latex} \\right) = {sp.latex(derivative)} $$."
            ),
            "simplification": f"F(x) = {result_latex} + C",
            "final_answer": f"{result_latex} + C"
        }

    def _solve_derivative(self, text: str) -> Dict[str, str]:
        """Differentiates expression and simplifies."""
        target_str = self._extract_target(text, ["diff", "derivative", "differentiate", "d/dx"])
        expr = self._parse(target_str)
        
        result = sp.diff(expr, self.x)
        simplified = sp.simplify(result)
        
        problem_latex = sp.latex(sp.Derivative(expr, self.x))
        result_latex = sp.latex(simplified)
        
        return {
            "problem": f"\\frac{{d}}{{dx}} \\left( {sp.latex(expr)} \\right)",
            "steps": (
                f"- Identified differentiation target: $$ f(x) = {sp.latex(expr)} $$.\n"
                "- Applied standard calculus differentiation rules (power, product, chain rules)."
            ),
            "simplification": f"f'(x) = {result_latex}",
            "final_answer": result_latex
        }

    def _solve_limit(self, text: str) -> Dict[str, str]:
        """Solves limits symbolically as x -> target."""
        # e.g. limit(sin(x)/x,x,0)
        match = re.search(r'limit\((.*?),(.*?),(.*?)\)', text)
        if match:
            expr_str, var_str, target_str = match.groups()
            expr = self._parse(expr_str)
            var = sp.Symbol(var_str)
            target = self._parse(target_str)
        else:
            # Fallback x -> 0 limit parsing
            target_str = self._extract_target(text, ["limit"])
            expr = self._parse(target_str)
            var = self.x
            target = 0
            
        result = sp.limit(expr, var, target)
        
        return {
            "problem": f"\\lim_{{{var} \\to {sp.latex(target)}}} \\left( {sp.latex(expr)} \\right)",
            "steps": (
                f"- Evaluated behavior of $$ f({var}) = {sp.latex(expr)} $$ as $$ {var} \\to {sp.latex(target)} $$.\n"
                "- Evaluated limit points symbolically using analytical mathematical convergence."
            ),
            "simplification": f"L = {sp.latex(result)}",
            "final_answer": sp.latex(result)
        }

    def _solve_equation(self, text: str) -> Dict[str, str]:
        """Solves algebraic equations symbolically."""
        # Strip solve keyword
        equation_str = text.replace("solve", "")
        
        # Split into left and right sides
        if "=" in equation_str:
            lhs_str, rhs_str = equation_str.split("=")
            lhs = self._parse(lhs_str)
            rhs = self._parse(rhs_str)
            eq = sp.Eq(lhs, rhs)
            expr = lhs - rhs
        else:
            expr = self._parse(equation_str)
            eq = sp.Eq(expr, 0)
            
        solutions = sp.solve(expr, self.x)
        solutions_latex = ", ".join([sp.latex(sol) for sol in solutions])
        factored = sp.factor(expr)
        factored_latex = sp.latex(factored)

        if factored != expr and len(solutions) > 0:
            steps = (
                f"We move everything to one side:\n\n$$ {sp.latex(expr)} = 0 $$\n\n"
                f"Then we factor the expression:\n\n$$ {factored_latex} = 0 $$\n\n"
                "Now each factor can equal zero, so we solve each part and collect the roots."
            )
        else:
            steps = (
                f"We move everything to one side:\n\n$$ {sp.latex(expr)} = 0 $$\n\n"
                "Then we solve the equation symbolically and simplify the roots."
            )
        
        return {
            "problem": sp.latex(eq),
            "steps": steps,
            "simplification": f"x \\in \\left\\{{ {solutions_latex} \\right\\}}",
            "final_answer": solutions_latex
        }

    def _solve_arithmetic(self, text: str) -> Dict[str, str]:
        """Solves pure numeric evaluations mathematically."""
        expr = self._parse(text)
        result = sp.simplify(expr)
        
        # If float represents an exact integer, convert it
        if result.is_number and result == int(result):
            result = int(result)
        else:
            result = sp.N(result, 8)
            
        return {
            "problem": sp.latex(expr),
            "steps": (
                f"- Parsed algebraic arithmetic statement: $$ {sp.latex(expr)} $$.\n"
                "- Evaluated core constants and operations."
            ),
            "simplification": f"V = {result}",
            "final_answer": str(result)
        }

    def _extract_target(self, text: str, keywords: list) -> str:
        """Helper to extract math expressions inside parentheses or after keywords."""
        for kw in keywords:
            text = text.replace(kw, "")
        # Remove outer enclosing parentheses if they exist, e.g. (x**2)
        if text.startswith("(") and text.endswith(")"):
            text = text[1:-1]
        return text

    def _parse(self, text: str):
        return parse_expr(
            text,
            transformations=self.transformations,
            local_dict={"x": self.x, "y": self.y, "sin": sp.sin, "cos": sp.cos, "tan": sp.tan, "sqrt": sp.sqrt},
            evaluate=True,
        )

sympy_solver = SympySolver()
